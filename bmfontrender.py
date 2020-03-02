#!/usr/bin/env python3
"""

Bitmap font rendering program

Copyright 2015-2016 Damian Yerrick

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""
from __future__ import with_statement, division, print_function
import os
import sys
import tempfile
import bisect
import re
from subprocess import Popen
try:
    from PIL import Image
except ImportError:
    print("Pillow (Python Imaging Library) is not installed.\n"
          "See https://pillow.readthedocs.org/installation.html",
          file=sys.stderr)
    sys.exit(1)
try:
    if str is not bytes:
        # In Python 3, both a package and a module are named tkinter.
        # This can be confusing.  IDLE hides this somewhat.
        # https://stackoverflow.com/a/28375781/2738262
        import tkinter
        from tkinter import filedialog as tkFileDialog
        from tkinter import messagebox as tkMessageBox
        xrange = range
    else:
        import Tkinter as tkinter, tkFileDialog, tkMessageBox
except ImportError:
    print("Tkinter (Python interface to Tk) is not installed.", file=sys.stderr)
    if os.name == 'posix':
        print("Debian and Ubuntu package Tkinter separately from Python.  Try this:\n"
              "    sudo apt install python3-pil.imagetk",
              file=sys.stderr)
    sys.exit(1)
try:
    from PIL import ImageTk
except ImportError:
    print("Tk and Pillow are installed, but not the module that connects the two.\n"
          "Debian and Ubuntu, for example, provide this separately:\n"
          "    sudo apt install python3-pil.imagetk",
          file=sys.stderr)
    sys.exit(1)

colorRE = re.compile('#([0-9a-fA-F]+)$')

def parse_color(s):
    m = colorRE.match(s)
    if m:
        hexdigits = m.group(1)
        if len(hexdigits) == 3:
            return tuple(int(c, 16) * 17 for c in hexdigits)
        elif len(hexdigits) == 6:
            return tuple(int(hexdigits[i:i + 2], 16) for i in range(0, 6, 2))
        else:
            return None
    return None

# if you get ImportError, have your administrator install tkinter
# and Pillow:
# sudo apt-get install python-imaging-tk    # for Python 2.7
# sudo apt-get install python3-imaging-tk   # for Python 3.3+

def vwfscan_line(pxa, y, width, maxwidth, sepColor):
    """Scan along a scanline for runs of pixels other than the separator color."""
    slices = []
    for x in xrange(width):
        is_active = slices and slices[-1][1] is None
        is_opaque = pxa[x, y] != sepColor
        is_ending = is_active and (not is_opaque
                                   or slices[-1][0] + maxwidth <= x)
        is_starting = is_opaque and (is_ending or not is_active)
        if is_ending:
            slices[-1] = (slices[-1][0], y, x)
        if is_starting:
            slices.append((x, None))
    # If last pixel on the line was not a separator
    if slices and slices[-1][1] is None:
        slices[-1] = (slices[-1][0], y, width)
    return slices

class PILtxt(object):
    def __init__(self, im, glyphWidth, glyphHeight, maxWidth,
                 ranges=0):
        """Load a font.

im - a PIL image
glyphWidth - width of cell in which each glyph is left-aligned,
or None for proportional
glyphHeight - height of a row of glyphs
maxWidth - maximum width of a proportional glyph
ranges -- an iterable of (first CP, last CP + 1, first glyph index)
or an integer first CP (if glyphs correspond to contiguous CPs)

"""
        self.img = im
        self.cw = glyphWidth
        self.ch = glyphHeight
        if glyphWidth is None:  # Proportional font
            if len(im.mode) == 1:
                (xparentColor, sepColor) = im.getextrema()
            else:
                sepColor = (255, 0, 255)
            vwf_table = []
            pxa = im.load()
            w, h = im.size
            for yt in xrange(0, h, glyphHeight):
                vwf_table.extend(vwfscan_line(pxa, yt, w, maxWidth, sepColor))
        else:  # Monospace font
            vwf_table = None
        self.vwf_table = vwf_table

        # Translate first code point to code point range
        try:
            iter(ranges)
        except TypeError:
            self.ranges = [(ranges, ranges + self.num_glyphs(), 0)]
        else:
            self.ranges = sorted(ranges)

    def num_glyphs(self):
        """Count glyphs in the bitmap."""
        if self.vwf_table:
            return len(self.vwf_table)
        num_cols = (self.img.size[0] // self.cw)
        num_rows = (self.img.size[1] // self.ch)
        return num_rows * num_cols

    def codepoint_range(self):
        return (min(row[0] for row in self.ranges),
                max(row[1] for row in self.ranges))

    def cp_to_glyph(self, cp):
        try:
            cp = ord(cp)
        except TypeError:
            pass
        idx = bisect.bisect(self.ranges, (cp, cp))
        if idx > 0 and (idx >= len(self.ranges) or self.ranges[idx][0] > cp):
            idx -= 1
        l, h, run_base_cp = self.ranges[idx]
        if l <= cp < h:
            return (cp - l) + run_base_cp
        return None

    def __contains__(self, cp):
        """'r' in self: Return whether the code point has a glyph."""
        return self.cp_to_glyph(cp) is not None

    def text_size(self, txt):
        txt1 = [self.cp_to_glyph(c) or 0 for c in txt]
        if not txt1:
            w = 0
        elif self.vwf_table:
            if max(txt1) >= len(self.vwf_table):
                raise IndexError(
                    "glyphid %d >= vwf_table length %d; malformed foni?"
                    % (max(txt1), len(self.vwf_table))
                )
            w = 0
            for c in txt1:
                l, _, r = self.vwf_table[c]
                w += r - l
        else:  # fixed width
            w = sum(self.cw for c in txt1)
        return (w, self.ch)

    def textout(self, dstSurface, txt, x, y):
        txt1 = [self.cp_to_glyph(c) or 0 for c in txt]
        startx = x
        wids = self.vwf_table
        if not wids:
            rowsz = self.img.size[0] // self.cw
        for c in txt1:
            if wids:
                (l, t, r) = wids[c]
            else:
                t = c // rowsz * self.ch
                if t >= self.img.size[1]:
                    continue
                l = c % rowsz * self.cw
                r = l + self.cw
            srcarea = self.img.crop((l, t, r, t + self.ch))
            dstSurface.paste(srcarea, (x, y))
            x += r - l
        return (startx, y, x, y + self.ch)

    @staticmethod
    def parse_chars(ranges):
        ranges = [r.strip().split('-', 1)
                  for line in ranges
                  for r in line.split(',')]
        rangetoglyphid = []
        glyphidbase = 0
        for line in ranges:
            firstcp = int(line[0], 16)
            lastcp = int(line[-1], 16) + 1
            rangetoglyphid.append((firstcp, lastcp, glyphidbase))
            glyphidbase += lastcp - firstcp
        rangetoglyphid.sort()
        return rangetoglyphid

    @staticmethod
    def fromfonifile(filename):
        with open(filename, 'rU') as infp:
            lines = [line.strip().split('=', 1)
                     for line in infp]
        lines = [[line[0].rstrip(), line[1].lstrip()]
                 for line in lines
                 if len(line) == 2 and not line[0].startswith('#')]
        args = dict(lines)
        args['chars'] = [line[1] for line in lines if line[0] == 'chars']
        ranges = PILtxt.parse_chars(args['chars'])
        imname = os.path.join(os.path.dirname(filename), args['image'])
        im = Image.open(imname)
        height = int(args['height'])
        try:
            width = int(args['width'])
        except KeyError:
            width = None
        if not ranges:
            try:
                ranges = int(args['firstcp'], 0)
            except KeyError:
                ranges = 32
        try:
            maxwidth = int(args['maxwidth'], 0)
        except KeyError:
            maxwidth = im.size[0]
        return PILtxt(im, width, height, maxwidth, ranges), args

class App:

    def __init__(self, master):

        self.root = master
        master.wm_title("bitmap font renderer")
        self.texttorender = None
        self.font = self.bgcolor = None
        self.tmpdir = None
        self.previewimage = Image.new('1', (128, 16))
        self.saved_count = 0

        menubar = tkinter.Menu(root)
        menubar.add_command(label="Font", command=self.choose_font)
        menubar.add_command(label="Render", command=self.say_hi)
        menubar.add_command(label="Save As", command=self.save_as)
        menubar.add_command(label="GIMP", command=self.open_in_gimp)
        menubar.add_command(label="Quit", command=root.quit)
        master.config(menu=menubar)

        frame = tkinter.Frame(master)
        frame.pack()
        self.previewarea = tkinter.Canvas(frame, height=100)
        self.previewarea.pack()
        self.update_preview()

        self.texttorender = tkinter.Text(frame, takefocus=1)
        self.texttorender.pack()
        self.texttorender.bind('<Control-Return>', self.say_hi)
        self.texttorender.focus()

    def __del__(self):
        self.close()

    def close(self):
        if self.tmpdir is not None:
            self.tmpdir.cleanup()
            self.tmpdir = None

    def update_preview(self):
        self.previewarea.delete(tkinter.ALL)
        self.previewpimage = ImageTk.PhotoImage(self.previewimage)
        self.previewarea.config(width=self.previewimage.size[0],
                                height=self.previewimage.size[1])
        self.previewarea.create_image((0, 0), image=self.previewpimage, anchor=tkinter.NW)

    def render_text(self, text):
        text = text.split('\n')
        boxes = [self.font.text_size(line) for line in text]
        w = max(line[0] for line in boxes)
        h = sum(line[1] for line in boxes)
        im = Image.new('RGB', (w, h), self.bgcolor)
        y = 0
        for (lw, lh), line in zip(boxes, text):
            self.font.textout(im, line, 0, y)
            y += lh
        return im

    def render_cur_text(self):
        text = (self.texttorender.get("1.0", tkinter.END).rstrip()
                if self.texttorender and self.font
                else '')
        if text:
            return self.render_text(text)
        else:
            return False

    def say_hi(self, event=None):
        im = self.render_cur_text()
        if im:
            im.show()
        return 'break'  # return value that does preventDefault

    def save_as(self, event=None):
        options = {
            'defaultextension': '.png',
            'filetypes': [('all files', '.*'), ('PNG image', '.png'), ('Windows bitmap', '.bmp')],
            'parent': self.root,
            'title': "Save the text image as"
        }
        im = self.render_cur_text()
        if im:
            imfilename = tkFileDialog.asksaveasfilename(**options)
            im.save(imfilename)

    def open_in_gimp(self, event=None):
        if self.tmpdir is None:
            self.tmpdir = tempfile.TemporaryDirectory()
            print("Allocated temporary directory", self.tmpdir.name)
        im = self.render_cur_text()
        if not im:
            return
        # Can't use NamedTemporaryFile on Windows because its
        # resulting file is opened for exclusive access.
        self.saved_count += 1
        filename = os.path.join(self.tmpdir.name, 'image%04d.png' % self.saved_count)
        print("saving to", filename)
        im.save(filename)
        pid = Popen(["gimp", filename]).pid

    def choose_font(self, event=None):
        options = {
            'filetypes': [('foni file', '.foni'), ('all files', '.*')],
            'parent': self.root,
            'title': "Choose a font"
        }
        filename = tkFileDialog.askopenfilename(**options)
        if not filename: return 'break'
        try:
            font, args = PILtxt.fromfonifile(filename)
            bgcolorcode = args.get('bgcolor', '#000000')
            bgcolor = parse_color(bgcolorcode)
            if bgcolor is None:
                raise ValueError("%s: bad color for bgcolor: %s"
                                 % (filename, bgcolorcode))
            self.font, self.bgcolor = font, bgcolor
            sample_txt = 'A quick brown fox'
            if 'r' not in self.font:
                sample_txt = sample_txt.upper()
            self.previewimage = self.render_text(sample_txt)
            self.update_preview()
        except Exception as e:
            import traceback
            traceback.print_exc()
        return 'break'

root = tkinter.Tk()

app = App(root)

root.mainloop()
root.destroy()
