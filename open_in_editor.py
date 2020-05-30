#!/usr/bin/env python3
'''
This scripts allows opening your text editor from a link on a webpage/within a browser extension via MIME.
See a short [[https://karlicoss.github.io/promnesia-demos/jump_to_editor.webm][demo]].

It handles URIs like:

:    editor:///path/to/file:123
:    editor:///path/to/file?line=456

See =test_parse_uri= for more examples.

To install (register the MIME handler), run

:   python3 open_in_editor.py --install --editor emacs

See =--help= for the list of available editors. If you want to add other editors, the code should be easy to follow.

You can check that it works with

:   xdg-open 'editor:///path/to/some/file'

I haven't found any existing/mature scripts for this, *please let me know if you know of any*! I'd be quite happy to support one less script :)

The script was tested on *Linux only*! I'd be happy if someone contributes adjustments for OSX.
'''
# TODO make it editor-agnostic? although supporting line numbers will be trickier


PROTOCOL_NAME = 'editor'


def test_parse_uri():
    assert parse_uri('editor:///path/to/file') == (
        '/path/to/file',
        None,
    )

    assert parse_uri('editor:///path/with spaces') == (
        '/path/with spaces',
        None,
    )

    assert parse_uri('editor:///path/url%20encoded') == (
        '/path/url encoded',
        None,
    )

    # TODO not sure about whether this or lien= thing is preferrable
    assert parse_uri('editor:///path/to/file:10') == (
        '/path/to/file',
        10,
    )

    # todo not sure about this. I guess it's a more 'proper' way? non ambiguous and supports columns and other stuff potentially
    assert parse_uri('editor:///path/to/file?line=10') == (
        '/path/to/file',
        10,
    )

    assert parse_uri('editor:///path/to/file:oops/and:more') == (
        '/path/to/file:oops/and:more',
        None,
    )

    import pytest # type: ignore
    with pytest.raises(Exception):
        parse_uri('badmime://whatever')


def test_open_editor():
    import time
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        p = Path(td) / 'some file.org'
        p.write_text('''
line 1
line 2
line 3 ---- THIS LINE SHOULD BE IN FOCUS!
line 4
'''.strip())
        # todo eh, warns about swapfile
        for editor in EDITORS.keys():
            open_editor(f'editor://{p}:3', editor=editor)
        input("Press enter when ready")


import argparse
from pathlib import Path
import sys
import subprocess
from subprocess import check_call, run
import tempfile
from urllib.parse import unquote, urlparse, parse_qsl



def notify(what) -> None:
    # notify-send used as a user-facing means of error reporting
    run(["notify-send", what])


def error(what) -> None:
    notify(what)
    raise RuntimeError(what)


def install(editor: str) -> None:
    this_script = str(Path(__file__).absolute())
    CONTENT = f"""
[Desktop Entry]
Name=Open file in your text editor
Exec=python3 {this_script} --editor {editor} %u
Type=Application
Terminal=false
MimeType=x-scheme-handler/{PROTOCOL_NAME};
""".strip()
    with tempfile.TemporaryDirectory() as td:
        pp = Path(td) / 'open_in_editor.desktop'
        pp.write_text(CONTENT)
        check_call(['desktop-file-validate', str(pp)])
        dfile = Path('~/.local/share/applications').expanduser()
        check_call([
            'desktop-file-install',
            '--dir', dfile,
            '--rebuild-mime-info-cache',
            str(pp),
        ])
        print(f"Installed {pp.name} file to {dfile}", file=sys.stderr)
        print(f"""You might want to check if it works with "xdg-open '{PROTOCOL_NAME}:///path/to/some/file'" """, file=sys.stderr)


from typing import Tuple, Optional, List
Line = int
File = str
def parse_uri(uri: str) -> Tuple[File, Optional[Line]]:
    pr = urlparse(uri)
    if pr.scheme != PROTOCOL_NAME:
        error(f"Unexpected protocol {uri}")
        # not sure if a good idea to keep trying nevertheless?
    path = unquote(pr.path)

    linenum: Optional[int] = None

    line_s = dict(parse_qsl(pr.query)).get('line', None)
    if line_s is not None:
        linenum = int(line_s)
    else:
        spl = path.rsplit(':', maxsplit=1)

        # meh. not sure about this
        if len(spl) == 2:
            try:
                linenum = int(spl[1])
            except ValueError:
                # eh. presumably just a colon in filename
                pass
            else:
                path = spl[0]
    return (path, linenum)



def open_editor(uri: str, editor: str) -> None:
    uri, line = parse_uri(uri)

    # TODO seems that sublime and atom support :line:column syntax? not sure how to pass it through xdg-open though
    opener = EDITORS.get(editor, None)

    if opener is None:
        notify(f'Unexpected editor {editor}! Falling back to vim')
        opener = open_vim
    opener(uri, line)


def with_line(uri: File, line: Optional[Line]) -> List[str]:
    return [uri] if line is None else [f'+{line}', uri]


def open_default(uri: File, line:Optional[Line]) -> None:
    import shutil
    for open_cmd in ['xdg-open', 'open']:
        if shutil.which(open_cmd):
            # sadly no generic way to handle line for editors?
            check_call([open_cmd, uri])
            break
    else:
        error("No xdg-open/open found, can't figure out default editor. Fallback to vim!")
        open_vim(uri=uri, line=line)


def open_gvim(uri: File, line: Optional[Line]) -> None:
    args = with_line(uri, line)
    cmd = [
        'gvim',
        *args,
    ]
    check_call(['gvim', *args])


def open_vim(uri: File, line: Optional[Line]) -> None:
    args = with_line(uri, line)
    launch_in_terminal(['vim', *args])


def open_emacs(uri: File, line: Optional[Line]) -> None:
    args = with_line(uri, line)
    cmd = [
        'emacsclient',
        '--create-frame',
        # trick to run daemon if it isn't https://www.gnu.org/software/emacs/manual/html_node/emacs/emacsclient-Options.html
        '--alternate-editor=""',
        *args,
    ]
    # todo exec?
    check_call(cmd)
    return

    ### alternatively, if you prefer a terminal emacs
    cmd = [
        'emacsclient',
        '--tty',
        '--alternate-editor=""',
        *args,
    ]
    launch_in_terminal(cmd)
    ###


EDITORS = {
    'emacs'  : open_emacs,
    'vim'    : open_vim,
    'gvim'   : open_gvim,
    'default': open_default,
}


def launch_in_terminal(cmd: List[str]):
    import shlex
    check_call([
        # NOTE: you might need xdg-terminal on some systems
        "x-terminal-emulator",
        "-e",
        ' '.join(map(shlex.quote, cmd)),
    ])


# TODO could use that for column number? maybe an overkill though.. and most extractors won'tsupport it anyway
# https://www.gnu.org/software/emacs/manual/html_node/emacs/emacsclient-Options.html
def main():
    p = argparse.ArgumentParser()
    # TODO allow passing a binary?
    p.add_argument('--editor', type=str, default='vim', choices=EDITORS.keys(), help="Editor to use. 'default' means using your default GUI editor (discovered with open/xdg-open)")
    p.add_argument('--install', action='store_true', help='Pass to install (i.g. register MIME in your system)')
    p.add_argument('uri', nargs='?', help='URI to open + optional line number')
    p.add_argument('--run-tests', action='store_true', help='Pass to run unit tests')
    args = p.parse_args()
    if args.run_tests:
        # fuck, pytest can't run against a file without .py extension?
        test_parse_uri()
        test_open_editor()
    elif args.install:
        install(editor=args.editor)
    else:
        open_editor(args.uri, editor=args.editor)


if __name__ == '__main__':
    main()
