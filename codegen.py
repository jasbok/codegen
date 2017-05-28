#!/usr/bin/python3

'''
MIT License

Copyright (c) 2017 Stefan Alberts

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

import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time

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

        self._watched_dirs = []
        self._watched_files = {}
        self._recently_modified = {}

        self._do_print = False
        self._do_watch = False

        self._watch_interval = 15
        self._recent_interval = 2
        self._recent_ttl = 300
        self._watch_interval_counter = 0

    def add_schema(self, schema):
        self._schemas[schema] = self._load_schema(schema)

    def add_template(self, template):
        self._templates[template] = self._file_contents(template)

    def add_watched(self, dir):
        self._watched_dirs.append(dir)

    def print_to_stdout(self):
        self._do_print = True

    def start(self):
        if len(self._watched_dirs) > 0:
            running = True
            while running:
                if self._watch_interval_counter == 0:
                    modified = self._get_modified_files()
                    self._watch_interval_counter = self._watch_interval
                else:
                    modified = self._check_recently_modified()

                if len(modified) > 0:
                    for path, mod in modified.items():
                        filename, extention = os.path.splitext(path)

                        if extention == ".json":
                            schema = self._load_schema(path)
                            if schema is not None:
                                for template in self._get_templates_from_schema(schema):
                                    if "path" in template:
                                        contents = self._file_contents(template["path"])
                                        if "dest" in template:
                                            self._write_to_file(template["dest"], self._compile(contents, schema))

                try:
                    self._watch_interval_counter -= 1
                    time.sleep(self._recent_interval)
                except KeyboardInterrupt:
                    running = False
        else:
            self.process(self._schemas.values(), self._templates.values())

    def process(self, schemas, templates):
        for schema in schemas:
            for template in templates:
                compiled = self._compile(template, schema)

                if self._do_print:
                    print(compiled)

    def _compile(self, template, schema):
        result = ""
        content = template

        while True:
            match = REGEX_TOKEN.search(content)
            if match is None:
                result += content
                break

            result += content[:match.start()]
            content = self._process_token(match, schema) + content[match.end():]

        return result

    def _process_token(self, match, schema):
        token = self._get_token(match)
        op = token["operator"]
        if op == "$$" or op == "!!" or op == "^^":
            result = self._process_schema_token(token, schema)
        elif op == "%%":
            result = self._process_function_token(token)
        elif op == "@@":
            result = self._load_template(token["path"])

        return result or ""

    def _process_schema_token(self, token, schema):
            compiled = ""
            self._push_scope(token["operator"], token["path"])
            var = self._get_var(schema, self._scopes[-1])
            if var is not None:
                if token["expansion"] is not None:
                    select = token["select"]
                    if isinstance(var, list):
                        for index in self._get_selected_indices(var, select):
                            self._scopes[-1].append(index)
                            compiled += self._compile(token["expansion"], schema)
                            self._scopes[-1].pop()
                    else:
                        compile = select is None \
                            or isinstance(var, bool) and var == bool(select) \
                            or isinstance(var, int) and var == int(select) \
                            or isinstance(var, float) and var == float(select) \
                            or isinstance(var, str) and var == select
                        if compile:
                            compiled = self._compile(token["expansion"], schema)

                else:
                    compiled = str(var)
            self._pop_scope()
            return compiled

    def _process_function_token(self, token):
        path = token["path"]

        if path == "date":
            return datetime.datetime.now().strftime(token["expansion"])
        elif path == "git.name":
            return self._git_config("user.name")
        elif path == "git.email":
            return self._git_config("user.email")
        return ""

    def _git_config(self, property):
        return subprocess.check_output(["git", "config", property])     \
            .decode("utf-8")                                            \
            .replace("\n", "")

    def _get_token(self, match):
        return {
            "operator": match.group(1),
            "path": match.group(2),
            "select": match.group(3),
            "expansion": match.group(4),
        }

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
                token = self._get_token(match)

                if token["operator"] == "@@":
                    var = self._load_template(token["path"])

        return var

    def _load_schema(self, path):
        try:
            with open(path) as data_file:
                return json.load(data_file)
        except json.decoder.JSONDecodeError:
            print("Unable to parse json: ", path)
        except IOError:
            print("An IO error occurred while loading schema: ", path)
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

    def _write_to_file(self, path, contents):
        os.makedirs(os.path.dirname(path), exist_ok=True)

        try:
            with open(path, 'w') as file:
                file.write(contents)
        except IOError:
            print("Unable to write to file: ", path)

    def _get_modified_files(self):
        results = {}

        for dir in self._watched_dirs:
            for path in glob.glob(dir + '/**', recursive=True):
                if not os.path.isdir(path):
                    results[path] = os.path.getmtime(path)

        diff = {
                    key: value for key, value in results.items()
                    if key not in self._watched_files or
                    value - self._watched_files[key] > 0
               }
        self._watched_files = results

        curr = time.time()
        self._recently_modified = {
            key: value
            for key, value in self._watched_files.items()
            if curr - value < self._recent_ttl
        }

        return diff

    def _check_recently_modified(self):
        modified = {}
        for path, old in self._recently_modified.items():
            new = os.path.getmtime(path)
            if new - old > 0.0:
                self._recently_modified[path] = new
                self._watched_files[path] = new
                modified[path] = new
        return modified

    def _get_templates_from_schema(self, schema):
        if "__codegen__" in schema and "templates" in schema["__codegen__"]:
            return [template for template in schema["__codegen__"]["templates"]]
        return []


def main():
    codegen = Codegen()

    def parse_arg(arg, val):
        if arg == "-t" or arg == "--templates":
            for template in val.split(","):
                codegen.add_template(template)
        elif arg == '-s' or arg == "--schemas":
            for schema in val.split(","):
                codegen.add_schema(schema)
        elif arg == "-w" or arg == "--watch":
            for dir in val.split(","):
                codegen.add_watched(dir)
        elif arg == "-p" or arg == "--print":
            codegen.print_to_stdout()

    for i, arg in enumerate(sys.argv):
        if i == 0:
            continue

        if arg[0] != "-":
            filename, extension = os.path.splitext(arg)
            if extension == ".json":
                codegen.add_schema(arg)
            elif extension == ".template":
                codegen.add_template(arg)
        else:
            split = arg.split("=")

            if len(split) == 2:
                arg = split[0]
                val = split[1]
            else:
                val = None

            parse_arg(arg, val)

    codegen.start()


if __name__ == "__main__":
    main()
