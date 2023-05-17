#!/usr/bin/env python3
'''Parse TopCell.v and count number of instances of each primitive in TopCell module.
'''

import re

from collections import Counter, namedtuple
from textwrap import indent


Token = namedtuple('Token', ['type', 'value', 'line', 'column'])


class Design:
    'Verilog file' 

    def __init__(self, modules):
        self.modules = {module.name: module for module in modules}

    def count_instances(self, module):
        'Count number of instances of each primitive in a given module.'
        return self.modules[module].count_instances(self.modules)

    def __str__(self):
        return '\n\n'.join(map(str, self.modules.values()))


class Module:
    'Verilog module'

    def __init__(self, name, params, nets, instances):
        self.name = name
        self.params = params
        self.nets = nets
        self.instances = instances
        self.cntr = None

    def count_instances(self, modules):
        'Count number of instances of each primitive in this module.'
        if self.cntr is not None:
            return self.cntr
        self.cntr = Counter()
        for instance in self.instances:
            module = modules.get(instance.type)
            self.cntr[instance.type] += 1
            if module is not None:
                self.cntr += module.count_instances(modules)
        return self.cntr

    def __str__(self):
        params = ', '.join(map(str, self.params))
        nets = ',\n'.join(map(str, self.nets))
        nets = indent(nets, '    ')
        instances = ',\n'.join(map(str, self.instances))
        instances = indent(instances, '    ')
        return f'Module(\n' \
               f'  name={self.name},\n' \
               f'  params=[{params}],\n' \
               f'  nets=[\n' \
               f'{nets}],\n' \
               f'  instances=[\n' \
               f'{instances}]\n)'


class Net:
    'Declaration of Verilog input, output, or wire'

    def __init__(self, kind, name, msb, lsb):
        self.type = kind
        self.name = name
        self.msb = msb
        self.lsb = lsb

    def __str__(self):
        return f'Net(type={self.type}, name={self.name}, msb={self.msb}, lsb={self.lsb})'


class Instance:
    'Verilog module instance'

    def __init__(self, kind, name, args):
        self.type = kind
        self.name = name
        self.args = args

    def __str__(self):
        args = ',\n'.join(map(str, self.args))
        args = indent(args, '    ')
        return f'Instance(\n  type={self.type},\n  name={self.name},\n  args=[\n{args}])'


class Argument:
    'Argument of Verilog module instance'

    def __init__(self, param, arg, msb, lsb):
        self.param = param
        self.arg = arg
        self.msb = msb
        self.lsb = lsb

    def __str__(self):
        return f'Argument(param={self.param}, arg={self.arg}, msb={self.msb}, lsb={self.lsb})'


class Scanner:
    'Verilog scanner'

    regexes = {'COMMENT':    r'//.*\n',
               'NEWLINE':    r'\n',
               'NUMBER':     r'\d+',
               'IDENTIFIER': r'\w+',
               'PUNCTUATOR': r'[\(\)\[\]:\.,;]',
               'WHITESPACE': r'([ \t]+)',
               'MISMATCH':   r'.'}
    regex = '|'.join(f'(?P<{pair[0]}>{pair[1]})' for pair in regexes.items())

    keywords = ['module', 'endmodule', 'input', 'output', 'wire']

    def scan(self, inp):
        'Perform lexical analysis on Verilog input and return a generator with tokens.'
        line = 1
        start = 0
        for match in re.finditer(self.regex, inp):
            kind = match.lastgroup
            value = match.group()
            column = match.start() - start + 1
            if kind == 'NUMBER':
                value = int(value)
            elif kind == 'IDENTIFIER' and value in self.keywords:
                kind = value
            elif kind == 'PUNCTUATOR':
                kind = value
            elif kind in ['COMMENT', 'NEWLINE']:
                start = match.end()
                line += 1
                continue
            elif kind == 'WHITESPACE':
                continue
            elif kind == 'MISMATCH':
                raise RuntimeError(f'Unexpected token {value!r} on column {column} of line {line}')
            yield Token(kind, value, line, column)


class Parser:
    'Verilog parser'

    def __init__(self):
        self.token_gen = None
        self.token = None
        self.next_token = None

    def parse(self, inp):
        'Parse provided Verilog input and returns data structure representing it.'
        scanner = Scanner()
        self.token_gen = scanner.scan(inp)
        self._advance()
        parsed_design = self._parse_file()
        if self.next_token is not None:
            raise SyntaxError('Unexpected end of file')
        return parsed_design

    def _parse_file(self):
        'EBNF: file = {"module" identifier "(" params ")" ";" nets instances "endmodule"}'
        modules = []
        while self._accept('module'):
            self._expect('IDENTIFIER')
            name = self.token.value
            self._expect('(')
            params = self._parse_params()
            self._expect(')')
            self._expect(';')
            nets = self._parse_nets()
            instances = self._parse_instances()
            self._expect('endmodule')
            modules.append(Module(name, params, nets, instances))
        return Design(modules)

    def _parse_params(self):
        'EBNF: params = identifier {"," identifier}'
        params = []
        self._expect('IDENTIFIER')
        params.append(self.token.value)
        while self._accept(','):
            self._expect('IDENTIFIER')
            params.append(self.token.value)
        return params

    def _parse_nets(self):
        'EBNF: {("output" | "input" | "wire") [dimensions] identifier ";"}'
        outputs = []
        while self._accept('output') or self._accept('input') or self._accept('wire'):
            kind = self.token.type
            msb, lsb = self._parse_dimensions()
            self._expect('IDENTIFIER')
            name = self.token.value
            self._expect(';')
            outputs.append(Net(kind, name, msb, lsb))
        return outputs

    def _parse_dimensions(self):
        'EBNF: dimensions = ["[" number ":" number "]"]'
        if self._accept('['):
            self._expect('NUMBER')
            msb = self.token.value
            self._expect(':')
            self._expect('NUMBER')
            lsb = self.token.value
            self._expect(']')
            return msb, lsb
        return 0, 0

    def _parse_instances(self):
        'EBNF: instance = {identifier identifier "(" args ")" ";"}'
        instances = []
        while self._accept('IDENTIFIER'):
            kind = self.token.value
            self._expect('IDENTIFIER')
            name = self.token.value
            self._expect('(')
            args = self._parse_args()
            self._expect(')')
            self._expect(';')
            instances.append(Instance(kind, name, args))
        return instances

    def _parse_args(self):
        'EBNF: args = arg {"," arg}'
        args = []
        args.append(self._parse_arg())
        while self._accept(','):
            args.append(self._parse_arg())
        return args

    def _parse_arg(self):
        'EBNF: arg = "." identifier "(" identifier ["[" number [":" number] "]"] ")"'
        self._expect('.')
        self._expect('IDENTIFIER')
        param = self.token.value
        self._expect('(')
        self._expect('IDENTIFIER')
        arg = self.token.value
        msb = 0
        lsb = 0
        if self._accept('['):
            self._expect('NUMBER')
            msb = self.token.value
            lsb = self.token.value
            if self._accept(':'):
                self._expect('NUMBER')
                lsb = self.token.value
            self._expect(']')
        self._expect(')')
        return Argument(param, arg, msb, lsb)

    def _expect(self, kind):
        'Read token from input and raise error if type of token is wrong.'
        if not self._accept(kind):
            line = self.token.line
            column = self.token.column
            raise SyntaxError(f'Expected {kind} on column {column} of line {line}')

    def _accept(self, kind):
        'Read token from input if it has given type.  Return true if successful.'
        if getattr(self.next_token, 'type', None) == kind:
            self._advance()
            return True
        return False

    def _advance(self):
        'Read token from input.'
        self.token = self.next_token
        try:
            self.next_token = next(self.token_gen)
        except StopIteration:
            self.next_token = None


if __name__ == '__main__':

    with open('TopCell.v', 'rt', encoding='utf-8') as input_file:
        text = input_file.read()

    parser = Parser()
    design = parser.parse(text)
    # print(design)

    cntr = design.count_instances('TopCell')
    #cntr = design.count_instances('cellB')
    for primitive, cnt in sorted(cntr.items()):
        print(f'{primitive:15} : {cnt} placements')
