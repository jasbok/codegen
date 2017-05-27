#!/usr/bin/python3

'''
MIT License

Copyright (c) [2017] [Stefan Alberts]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import json
import os
import re
import sys

R_SCOPE = "(\$\$|!!|\^\^|@@|%%)"
R_PATH = "(?:\.([\w|\.]*))?"
R_SELECT = "(?:\s*\[\[(.*?)\]\])?"
R_EXPANSION = "(?:[ |\t]*{{(?:[ |\t]*\n*)?(.*?)[ |\t]*}}(?:[ |\t]*\n)?)?"

REGEX_TOKEN = re.compile(
    R_SCOPE + R_PATH + R_SELECT + R_EXPANSION, re.DOTALL | re.MULTILINE)


class Codegen(object):

    def __init__(self):
        self._dest = ""
        self._files = {}
        self._schemas = {}
        self._templates = {}
        self._scopes = [[]]

    def add_schema(self, schema):
        self._schemas[schema] = self._load_schema(schema)

    def add_template(self, template):
        self._templates[template] = self._file_contents(template)

    def process(self):
        for schema in self._schemas.values():
            for template in self._templates.values():
                compiled = self._compile(template, schema)
                print(compiled)

    def _compile(self, template, schema):
        result = ""
        content = template

        while True:
            token = REGEX_TOKEN.search(content)
            if token is None:
                result += content
                break

            compiled = ""
            token_info = self._get_token_info(token)

            self._push_scope(token_info["operator"], token_info["path"])
            var = self._get_var(schema, self._scopes[-1])
            if var is not None:
                if token_info["expansion"] is not None:
                    select = token_info["select"]
                    if isinstance(var, list):
                        compiled = ""

                        for index in self._get_selected_indices(var, select):
                            self._scopes[-1].append(index)
                            compiled += self._compile(token_info["expansion"], schema)
                            self._scopes[-1].pop()
                    else:
                        compile = select is None \
                            or isinstance(var, bool) and var == bool(select) \
                            or isinstance(var, int) and var == int(select) \
                            or isinstance(var, float) and var == float(select) \
                            or isinstance(var, str) and var == select
                        if compile:
                            compiled = self._compile(token_info["expansion"], schema)

                else:
                    compiled = str(var)
            self._pop_scope()

            result += content[:token.start()]
            content = compiled + content[token.end():]

        return result

    def _get_token_info(self, token):
        info = {
            "operator": token.group(1),
            "path": token.group(2),
            "select": token.group(3),
            "expansion": token.group(4),
        }
        return info

    def _get_selected_indices(self, arr, select):
        indices = range(len(arr))

        if select is not None:
            slice = select.split(":")
            if len(slice) == 2:
                if slice[0] == '' and slice[1] != '':
                    indices = indices[:int(slice[1])]
                elif slice[0] != '' and slice[1] == '':
                    indices = indices[int(slice[0]):]
                else:
                    indices = indices[int(slice[0]):int(slice[1])]
            else:
                indices = [indices[int(select)]]

        return indices

    def _pop_scope(self):
        self._scopes.pop()

    def _push_scope(self, prefix, path):
        if prefix == "$$":
            scope = self._scopes[-1].copy()
        elif prefix == "!!":
            scope = []
        elif prefix == "^^":
            scope = self._scopes[-1][:-1].copy()

        if path is not None:
            for seg in path.split("."):
                if seg == "^^" > 0:
                    scope.pop()
                else:
                    scope.append(seg)

        self._scopes.append(scope)

    def _get_var(self, schema, scope):
        var = schema

        for seg in scope:
            if isinstance(var, list):
                if not isinstance(seg, int) or seg >= len(var):
                    return None
            elif seg not in var:
                return None
            var = var[seg]

        if isinstance(var, str):
            match = REGEX_TOKEN.match(var)
            if match:
                token_info = self._get_token_info(match)

                if token_info["operator"] == "@@":
                    var = self._load_template(token_info["path"])

        return var

    def _load_schema(self, path):
        with open(path) as data_file:
            return json.load(data_file)
        return None

    def _load_template(self, path):
        segments = path.split(".")
        segments[-1] += ".template"
        return self._file_contents(os.path.join(*segments))

    def _file_contents(self, path):
        if path not in self._files:
            try:
                with open(path, 'r') as file:
                    self._files[path] = file.read()
            except FileNotFoundError:
                print("The following file was not found: ", path)
                self._files[path] = None
        return self._files[path]


def main():
    codegen = Codegen()

    def parse_arg(arg, val):
        if arg == "-t" or arg == "--templates":
            for template in val.split(","):
                codegen.add_template(template)
        elif arg == '-s' or arg == "--schemas":
            for schema in val.split(","):
                codegen.add_schema(schema)

    for i, arg in enumerate(sys.argv):
        if i == 0:
            continue

        split = arg.split("=")

        if len(split) == 1:
            filename, extension = os.path.splitext(arg)
            if extension == ".json":
                codegen.add_schema(arg)
            elif extension == ".template":
                codegen.add_template(arg)
        else:
            parse_arg(split[0], split[1])

    codegen.process()


if __name__ == "__main__":
    main()
