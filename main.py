import os
import argparse
import subprocess
import math
from PIL import Image
from pdf2image import convert_from_path, exceptions as pdf2ex
from pydriller import RepositoryMining


class Renderer:
    def __init__(self, img_size, page_size, first_page=None, last_page=None):
        '''
        img_size: (w,h) dimensions of the output image
        page_size: (w,h) dimensions of on page that is printed onto the output image.
                   Images are arranged in a row-wise fashion, but overflows where the image is to small to house all pages are not handled
        first_page: first page to render (inclusive)
        last_page: last page to render (inclusive)
        '''
        self.img_size = (max(100, img_size[0]), max(100, img_size[1]))
        self.page_size = (max(10, page_size[0]), max(10, page_size[1]))
        self.first_page = first_page
        self.last_page = last_page

    def _layout_pages(self, canvas, pages):
        '''
        Aranges all pages on the canvas. Pages are distributed onto the canvas in a row-wise fashion and extra space is divided evenly to both sides.
        canvas: PIL image onto which the pages are printed
        pages: list of PIL images that are printed onto the canvas
        returns the canvas with the prints on it
        '''
        imgw, imgh = self.img_size
        pw, ph = self.page_size
        pages_per_row = math.floor(imgw / pw)
        margin = math.floor((imgw - pages_per_row * pw) / 2)
        for i in range(len(pages)):
            canvas.paste(pages[i], (margin + pw * math.floor(i % pages_per_row), ph * math.floor((i / pages_per_row))))
        return canvas

    def _create_canvas(self):
        '''
        Creates a new canvas with white background
        '''
        return Image.new("RGBA", self.img_size, (255, 255, 255, 255))

    def render(self, document, prefix=""):
        '''
        Renders all pages of a PDF file into an image that is stored into the cwd as X_digest.png, where X is a prefix parameter.
        document: path to the PDF file
        prefix: prefix (eg running number) for the output image
        returns a tuple consisting of the name of the new file and the PIL object itself
        '''
        canvas = self._create_canvas()
        pages = convert_from_path(document, size=self.page_size, first_page=self.first_page, last_page=self.last_page)
        self._layout_pages(canvas, pages)
        path = prefix + "_digest.png"
        canvas.save(path)
        print("saved image as %s" % (path,))
        return (path, canvas)


class GitHelper:
    def __init__(self, renderer, src_repository, compilation_command, outpath, subdirectory=""):
        self.renderer = renderer
        self.src_repository = src_repository
        self.subdirectory = subdirectory
        self.outpath = outpath
        self.cwd = os.path.join(src_repository, subdirectory)
        self.compilation_command = compilation_command

    def hashes(self):
        '''
        returns the hashes of all versions of the git repository
        '''
        return [commit.hash for commit in RepositoryMining(self.src_repository).traverse_commits()]

    def checkout(self, hash):
        '''
        Checks out a revision. WARNING! THIS USES THE FORCE CHECKOUT!
        hash: the hash of the revision to check out
        '''
        print("checking out hash %s" % (hash,))
        process = subprocess.Popen(["git", "checkout", "-f", hash], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.src_repository)
        stdout, stderr = process.communicate()
        # print(stdout)
        print(stderr)

    def compile_pdf(self):
        '''
        Compiles the PDF using the command given in the constructor
        '''
        print("compiling pdf using command %s" % (self.compilation_command,))
        process = subprocess.Popen(self.compilation_command.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.cwd)
        stdout, stderr = process.communicate()
        # print(stdout)

    def run(self, start_hash=None, end_hash=None, gif_path=None):
        '''
        Runs the utility
        start_hash: hash of revision at which to start (inclusive). If None is passed, starts at very first commit.
        end_hash: hash of the revision at which to end (inclusive) If None is passed, runs all the way to the last commit.
        gif_path: path to the output GIF. If None is passed, no GIF is generated after all frames have been made.
        '''
        frames = []
        prefix = 1
        hashes = self.hashes()
        if start_hash is not None:
            while len(hashes) > 0 and hashes[0] != start_hash:
                hashes.pop(0)
        stop = len(hashes) == 0
        while not stop:
            hash = hashes.pop(0)
            try:
                self.checkout(hash)
                self.compile_pdf()
                path, img = self.renderer.render(self.outpath, prefix=str(prefix))
                frames.append(img)
            except pdf2ex.PDFPageCountError:
                print("could not open the PDF for hash %s. Maybe this revision does not compile properly? Skipping this revision..." % (hash,))

            prefix += 1
            stop = hash == end_hash or len(hashes) == 0

        if gif_path is not None:
            img, *imgs = frames
            img.save(fp=gif_path, format='GIF', append_images=imgs, save_all=True, duration=200, loop=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", help="path to the repository", type=str, required=True)
    parser.add_argument("--command", help="command to compile the PDF, eg pdflatex or make. If the command should not be executed from the root, but from a subdirectory, use the --subdirectory switch", type=str, required=True)
    parser.add_argument("--pdfpath", help="path to where the PDF will be found after compilation is done. Depends on how you generate your PDF (see --command switch)", type=str, required=True)
    parser.add_argument("--subdirectory", help="subdirectory within the repository from which the command is run", type=str, default=None)
    parser.add_argument("--gifpath", help="path to the output gif generated from the frames", type=str, default=None)
    parser.add_argument("--framewidth", help="width of the frames", type=int, default=800)
    parser.add_argument("--frameheight", help="height of the frames", type=int, default=600)
    parser.add_argument("--pagewidth", help="width of one page within each frame", type=int, default=80)
    parser.add_argument("--pageheight", help="height of one page within each frame", type=int, default=100)
    parser.add_argument("--starthash", help="revision hash from which the tool should start (inclusive)", type=str, default=None)
    parser.add_argument("--endhash", help="revision hash at which the tool should end (inclusive)", type=str, default=None)
    args = parser.parse_args()

    renderer = Renderer((args.framewidth, args.frameheight), (args.pagewidth, args.pageheight))
    gh = GitHelper(renderer, args.repository, args.command, args.pdfpath, subdirectory=args.subdirectory)
    gh.run(start_hash=args.starthash, end_hash=args.endhash, gif_path=args.gifpath)


if __name__ == '__main__':
    main()
