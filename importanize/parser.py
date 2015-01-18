# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
import re

from .statements import DOTS, ImportLeaf, ImportStatement
from .utils import list_split, read


class Token(str):
    @property
    def is_comment(self):
        return self.startswith('#')


def get_file_artifacts(path):
    """
    Get artifacts for the given file.

    Parameters
    ----------
    path : str
        Path to a file

    Returns
    -------
    artifacts : dict
        Dictionary of file artifacts which should be
        considered while processing imports.
    """
    artifacts = {
        'sep': '\n',
    }

    lines = read(path).splitlines(True)
    if len(lines) > 1 and lines[0][-2:] == '\r\n':
        artifacts['sep'] = '\r\n'

    return artifacts


def find_imports_from_lines(iterator):
    """
    Find only import statements from enumerated iterator of file files.

    Parameters
    ----------
    iterator : generator
        Enumerated iterator which yield items
        ``(line_number, line_string)``

    Returns
    -------
    imports : generator
        Iterator which yields tuple of lines strings composing
        a single import statement as well as teh line numbers
        on which the import statement was found.
    """
    while True:

        try:
            line_number, line = next(iterator)
        except StopIteration:
            return

        # ignore comment blocks
        triple_quote = line.find('"""')
        if triple_quote >= 0 and line.find('"""', triple_quote + 3) < 0:
            inside_comment = True
            while inside_comment:
                try:
                    line_number, line = next(iterator)
                except StopIteration:
                    return
                inside_comment = not line.endswith('"""')
            # get the next line since previous is an end of a comment
            try:
                line_number, line = next(iterator)
            except StopIteration:
                return

        # if no imports found on line, ignore
        if not any([line.startswith('from '),
                    line.startswith('import ')]):
            continue

        line_numbers = [line_number]
        line_imports = [line]

        # if parenthesis found, consider new lines
        # until matching closing parenthesis is found
        if '(' in line and ')' not in line:
            while ')' not in line:
                line_number, line = next(iterator)
                line_numbers.append(line_number)
                line_imports.append(line)

        # if new line escape is found, consider new lines
        # until no escape character is found
        if line.endswith('\\'):
            while line.endswith('\\'):
                line_number, line = next(iterator)
                line_numbers.append(line_number)
                line_imports.append(line)

        yield line_imports, line_numbers


def tokenize_import_lines(import_lines):
    tokens = []

    for n, line in enumerate(import_lines):
        _tokens = []
        words = filter(None, re.split(r' +|[\(\)]|([,\\])|(#.*)', line))

        for i, word in enumerate(words):
            token = Token(word)
            # tokenize same-line comments before "," to allow to associate
            # a comment with specific import since pure Python
            # syntax does not do that because # has to be after ","
            # hence when tokenizing, comment will be associated
            # with next import which is not desired
            if token.is_comment and _tokens and _tokens[max(i - 1, 0)] == ',':
                _tokens.insert(i - 1, token)
            else:
                _tokens.append(token)

        tokens.extend(_tokens)

    # combine tokens between \\ newline escape
    segments = list_split(tokens, '\\')
    tokens = [Token('')]
    for segment in segments:
        tokens[-1] += segment[0]
        tokens += segment[1:]

    return [Token(i) for i in tokens]


def parse_import_statement(stem, line_numbers, **kwargs):
    """
    Parse single import statement into ``ImportStatement`` instances.

    Parameters
    ----------
    stem : str
        Import line stem which excludes ``"import"``.
        For example for ``import a`` import, simply ``a``
        should be passed.
    line_numbers : list
        List of line numbers which normalized to import stem.

    Returns
    -------
    statement : ImportStatement
        ``ImportStatement`` instances.
    """
    leafs = []

    if stem.startswith('.'):
        stem, leafs_string = DOTS.findall(stem)[0]

        # handle ``import .foo.bar``
        leafs_split = leafs_string.rsplit('.', 1)
        if len(leafs_split) == 2:
            stem += leafs_split[0]
            leafs_string = leafs_split[1]

        leafs.append(ImportLeaf(leafs_string))

    else:
        # handle ``import a.b as c``
        stem_split = stem.rsplit('.', 1)
        if len(stem_split) == 2 and ' as ' in stem:
            stem = stem_split[0]
            leafs_string = stem_split[1]
            leafs.append(ImportLeaf(leafs_string))

    # handle when ``as`` is present and is unnecessary
    # in import without leafs
    # e.g. ``import foo as foo``
    # if leaf is present, leaf will take care of normalization
    if ' as ' in stem and not leafs:
        name, as_name = stem.split(' as ')
        if name == as_name:
            stem = name

    return ImportStatement(line_numbers,
                           stem,
                           leafs,
                           **kwargs)


def parse_statements(iterable, **kwargs):
    """
    Parse iterable into ``ImportStatement`` instances.

    Parameters
    ----------
    iterable : generator
        Generator as returned by ``find_imports_from_lines``

    Returns
    -------
    statements : generator
        Generator which yields ``ImportStatement`` instances.
    """
    not_comment = lambda j: next(filter(lambda i: not i.is_comment, j))

    for import_lines, line_numbers in iterable:
        tokens = tokenize_import_lines(import_lines)

        if tokens[0] == 'import':
            for _tokens in list_split(tokens[1:], ','):
                stem = not_comment(_tokens)
                comments = filter(lambda i: i.is_comment, _tokens)
                yield parse_import_statement(
                    stem=stem,
                    line_numbers=line_numbers,
                    comments=comments,
                    **kwargs
                )

        else:
            stem, _leafs = list_split(tokens[1:], 'import')
            stem = not_comment(stem)
            _leafs = list(list_split(_leafs, ','))

            leafs = []
            for leaf in _leafs:
                _leaf = not_comment(leaf)
                comments = filter(lambda i: i.is_comment, leaf)
                leafs.append(ImportLeaf(_leaf, comments=comments))

            yield ImportStatement(
                line_numbers=line_numbers,
                stem=stem,
                leafs=leafs,
                **kwargs
            )
