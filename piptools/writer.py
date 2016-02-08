import os
from os.path import basename

from ._compat import ExitStack
from .click import unstyle
from .io import AtomicSaver
from .logging import log
from .utils import comment, format_requirement


class OutputWriter(object):
    def __init__(self, src_file, dst_file, dry_run, emit_header, emit_index, annotate,
                 default_index_url, index_urls):
        self.src_file = src_file
        self.dst_file = dst_file
        self.dry_run = dry_run
        self.emit_header = emit_header
        self.emit_index = emit_index
        self.annotate = annotate
        self.default_index_url = default_index_url
        self.index_urls = index_urls

    def _sort_key(self, ireq):
        return (not ireq.editable, str(ireq.req).lower())

    def write_header(self):
        if self.emit_header:
            yield comment('#')
            yield comment('# This file is autogenerated by pip-compile')
            yield comment('# Make changes in {}, then run this to update:'.format(basename(self.src_file)))
            yield comment('#')
            args = ''
            if not self.emit_index:
                args += '--no-index '
            if not self.annotate:
                args += '--no-annotate '
            yield comment('#    pip-compile {args}{filename}'.format(
                          args=args,
                          filename=basename(self.src_file)))
            yield comment('#')

    def write_index_options(self):
        if self.emit_index:
            emitted = False
            for index, index_url in enumerate(self.index_urls):
                if index_url.rstrip('/') == self.default_index_url:
                    continue
                flag = '--index-url' if index == 0 else '--extra-index-url'
                yield '{} {}'.format(flag, index_url)
                emitted = True
            if emitted:
                yield ''  # extra line of whitespace

    def _iter_lines(self, results, reverse_dependencies, primary_packages):
        for line in self.write_header():
            yield line
        for line in self.write_index_options():
            yield line

        UNSAFE_PACKAGES = {'setuptools', 'distribute', 'pip'}
        unsafe_packages = {r for r in results if r.name in UNSAFE_PACKAGES}
        packages = {r for r in results if r.name not in UNSAFE_PACKAGES}

        packages = sorted(packages, key=self._sort_key)
        unsafe_packages = sorted(unsafe_packages, key=self._sort_key)

        for ireq in packages:
            line = self._format_requirement(ireq, reverse_dependencies, primary_packages)
            yield line

        if unsafe_packages:
            yield ''
            yield comment('# The following packages are commented out because they are')
            yield comment('# considered to be unsafe in a requirements file:')

            for ireq in unsafe_packages:
                line = self._format_requirement(ireq, reverse_dependencies, primary_packages, include_specifier=False)
                yield comment('# ' + line)

    def write(self, results, reverse_dependencies, primary_packages):
        with ExitStack() as stack:
            f = None
            if not self.dry_run:
                f = stack.enter_context(AtomicSaver(self.dst_file))

            for line in self._iter_lines(results, reverse_dependencies, primary_packages):
                log.info(line)
                if f:
                    f.write(unstyle(line).encode('utf-8'))
                    f.write(os.linesep.encode('utf-8'))

    def _format_requirement(self, ireq, reverse_dependencies, primary_packages, include_specifier=True):
        line = format_requirement(ireq, include_specifier=include_specifier)
        if not self.annotate or ireq.name in primary_packages:
            return line

        # Annotate what packages this package is required by
        required_by = reverse_dependencies.get(ireq.name.lower(), [])
        if required_by:
            line = line.ljust(24)
            annotation = ', '.join(sorted(required_by))
            line += comment('  # via ' + annotation)
        return line