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


class Project(object):
    """Contains configs to generate project files."""
    def __init__(self, project_schema):
        if not isinstance(project_schema, Schema):
            raise ValueError("Project() - Expected Schema:", project_schema)

        self._project_schema = project_schema
        self._schemas = {}
        self._templates = {}

        if "schemas" in self._project_schema.json():
            for schema in self._project_schema.json()["schemas"]:
                spath = schema["path"]
                schema_config = {
                    "file": Schema(File(spath)),
                    "templates": {}
                }
                if "templates" in schema["templates"]:
                    for template in schema["templates"]:
                        tpath = template["path"]
                        self._templates[tpath] = {
                            "file": File(tpath)
                        }
                        schema_config["templates"][tpath] = {
                            "destination": self._templates["destination"]
                        }
                self._schemas[spath] = schema_config

    def __repr__(self):
        return "Project[schema='{}',schemas={}, templates={}]".format(
            self._project_schema,
            self._schemas.values(),
            self._templates.values())


class File(object):
    """Helper class for file operations."""
    def __init__(self, path):
        if not isinstance(path, str):
            raise ValueError(
                "File() - Expected string: ", path)

        self._path = path
        self._atime = None
        self._mtime = None
        self._contents = None

    def __repr__(self):
        return "File[path='{}', atime='{}', mtime='{}']".format(
            self._path, self._atime, self._mtime)

    def atime(self, no_cache=True):
        """Get the last access time."""
        if no_cache or self._atime is None:
            self._atime = None
            try:
                self._atime = os.path.getatime(self._path)
            except OSError as ex:
                print("File.atime - OS exception:", self._path, ex)

        return self._atime

    def mtime(self, no_cache=True):
        """Get the last modified time."""
        if no_cache or self._mtime is None:
            self._mtime = None
            try:
                self._mtime = os.path.getmtime(self._path)
            except OSError as ex:
                print("File.mtime - OS exception:", self._path, ex)

        return self._mtime

    def exists(self):
        """Checks whether file exists."""
        return os.path.isfile(self._path)

    def path(self):
        """Gets the file path."""
        return self._path

    def read(self, no_cache=True):
        """Reads the contents of the file."""
        if no_cache and self._mtime != self.mtime() or self._contents is None:
            self._contents = None
            try:
                with open(self._path, 'r') as file:
                    self._contents = file.read()
            except FileNotFoundError as ex:
                print("File.read - File not found:", self._path, ex)
            except IOError as ex:
                print("File.read - IO error on load:", self._path, ex)

        return self._contents

    def write(self, contents):
        """Writes the contents to cache and disk."""
        success = False
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, 'w') as file:
                file.write(contents)
                success = True
        except IOError as ex:
            print("File.write - An IO error occurred: ", self._path, ex)

        self.atime()
        self.mtime()

        return success

    def empty_cache(self):
        """Empties the cache."""
        self._atime = None
        self._mtime = None
        self._contents = None


class Token(object):
    """Contains functionality to read and store codegen tokens."""
    R_OPERATOR = r"(\$\$|!!|\^\^|@@|%%)"
    R_PATH = r"(?:\.([\w|\.]*))?"
    R_SELECT = r"(?:\s*\[\[(.*?)\]\])?"
    R_EXPANSION = r"(?:[ |\t]*{{(?:[ |\t]*\n*)?(.*?)[ |\t]*}}(?:[ |\t]*\n)?)?"

    REGEX_TOKEN = re.compile(
        R_OPERATOR + R_PATH + R_SELECT + R_EXPANSION, re.DOTALL | re.MULTILINE)

    def __init__(self, match):
        self.operator = match.group(1)
        self.path = match.group(2).split(".") if match.group(2) else []
        self.select = match.group(3)
        self.expansion = match.group(4)
        self.start = match.start()
        self.end = match.end()

    def __repr__(self):
        return "Token[operator='{}', path='{}', select='{}', expansion='{}', "\
                "start='{}', end='{}']".format(self.operator, self.path,
                                               self.select, self.expansion,
                                               self.start, self.end)

    def resolve_function(self):
        """Resolves and evaluates the function from the token path."""
        if self.path == ["date"]:
            return datetime.datetime.now().strftime(self.expansion)
        elif self.path == ["git", "name"]:
            return Git.config("user.name")
        elif self.path == ["git", "email"]:
            return Git.config("user.email")
        return None

    def resolve_template(self):
        """Resolves the template from the token path."""
        return File(os.path.join(*self.path) + ".template").read()

    def resolve_indices(self, lst):
        """Resolves the list indices from the token select."""
        indices = range(len(lst))

        if self.select is not None:
            index_slice = self.select.split(":")
            if len(index_slice) == 2:
                if index_slice[0] == '' and index_slice[1] != '':
                    indices = indices[:int(index_slice[1])]
                elif index_slice[0] != '' and index_slice[1] == '':
                    indices = indices[int(index_slice[0]):]
                else:
                    indices = indices[int(index_slice[0]):int(index_slice[1])]
            else:
                indices = [indices[int(self.select)]]

        return indices

    @staticmethod
    def find(content):
        """Finds the first token in the given string."""
        match = Token.REGEX_TOKEN.search(content)
        return Token(match) if match else None


class Schema(object):
    """Contains functionality to parse and view a json schema."""
    def __init__(self, file):
        if not isinstance(file, File):
            raise ValueError("Schema() - Expected File: ", file)

        self._file = file
        self._mtime = None
        self._json = None
        self.update()

    def __repr__(self):
        return "Schema[file={}]".format(self._file)

    def id(self):
        """Returns the id of the schema."""
        return self._file.path()

    def mtime(self):
        """Returns the last modified time of the schema."""
        return self._mtime

    def update(self):
        """Updates the schema if it has been modified."""
        updated = self._mtime != self._file.mtime()
        if updated:
            self._mtime = self._file.mtime()
            self._json = json.loads(self._file.read())
        return updated

    def json(self):
        """Returns the json contained in the schema."""
        return self._json

    def value(self, path, scope=None):
        """Gets the value corresponding with the path, None otherwise."""
        if isinstance(path, str):
            path = [path]
        elif not isinstance(path, list):
            raise ValueError(
                "Schema.variable - Expected str or list:", path)

        if scope is None:
            scope = []

        scope += path
        var = self._json
        for seg in scope:
            if isinstance(var, list):
                if not isinstance(seg, int) or seg >= len(var):
                    print("Segment index out of bounds ({}): {}".format(var,
                                                                        seg))
                    return None
            elif seg not in var:
                print("Segment not found in var '{}' ({}): {}".format(seg,
                                                                      scope,
                                                                      var))
                return None
            var = var[seg]

        return var


class Schema_Stack(object):
    """Manages the scope of a schema as a stack."""
    def __init__(self, schema):
        if not isinstance(schema, Schema):
            raise ValueError(
                "Schema_Stack() - Expected Schema: ", schema)

        self._schema = schema
        self._scopes = [[]]

    def push(self, token):
        """Push a token onto the stack."""
        if isinstance(token, Token):
            if token.operator == "$$":
                scope = self._scopes[-1].copy()
            elif token.operator == "!!":
                scope = []
            elif token.operator == "^^":
                scope = self._scopes[-1][:-1].copy()

            if token.path is not None:
                for seg in token.path:
                    if seg == "^^" > 0:
                        scope.pop()
                    else:
                        scope.append(seg)

            self._scopes.append(scope)
        elif isinstance(token, int):
            scope = self._scopes[-1].copy()
            scope.append(token)
            self._scopes.append(scope)
        else:
            raise ValueError("Compiler._push - Expected list or Token:", token)

    def pop(self):
        """Pops the top token from the stack."""
        self._scopes.pop()

    def value(self):
        """Gets the schema value associated with the top of the stack."""
        return self._schema.value(self._scopes[-1])


class Compiler(object):
    """Builds a template compiler from a given schema."""
    def __init__(self, schema):
        if not isinstance(schema, Schema):
            raise ValueError(
                "Compiler() - Expected Schema: ", schema)

        self._stack = Schema_Stack(schema)

    def compile(self, template):
        """Compiles a template using the compiler schema."""
        if isinstance(template, File):
            tmp = template.read()
        elif isinstance(template, str):
            tmp = template
        else:
            raise ValueError(
                "Compiler.compile - Expected str or File: ", template)

        out = ""
        token = Token.find(tmp)
        while token is not None:
            out += tmp[:token.start]
            tmp = self._resolve(token) + tmp[token.end:]
            token = Token.find(tmp)

        return out + tmp

    def _resolve(self, token):
        op = token.operator

        if op == "$$" or op == "!!" or op == "^^":
            result = self._resolve_value(token)
        elif op == "%%":
            result = token.resolve_function()
        elif op == "@@":
            result = token.resolve_template()

        return result or ""

    def _resolve_value(self, token):
        if not isinstance(token, Token):
            raise ValueError(
                "Compiler._resolve_value - Expected Token: ", token)

        self._stack.push(token)

        compiled = ""
        var = self._stack.value()
        if var is not None:
            if token.expansion is not None:
                if isinstance(var, list):
                    for index in token.resolve_indices(var):
                        self._stack.push(index)
                        compiled += self.compile(token.expansion)
                        self._stack.pop()
                else:
                    select = token.select
                    do_compile = select is None \
                        or isinstance(var, bool) and var == bool(select) \
                        or isinstance(var, int) and var == int(select) \
                        or isinstance(var, float) and var == float(select) \
                        or isinstance(var, str) and var == select
                    if do_compile:
                        compiled = self.compile(token.expansion)
            else:
                compiled = str(var)

        self._stack.pop()
        return compiled


class Git(object):
    """Helper class to get git config information."""
    @staticmethod
    def config(prop):
        """ Uses git config to check the value of a property."""
        result = None
        try:
            result = subprocess.check_output(["git", "config", prop])       \
                .decode("utf-8")                                            \
                .replace("\n", "")
        except subprocess.CalledProcessError as ex:
            print("Failed to retrived Git information: ", ex)
        return result


class File_Watcher(object):
    """Watches files for changes."""
    def __init__(self, dirs, active_time=600):
        self.dirs = dirs
        self.active_time = active_time
        self._watched = []
        self._modified = []
        self._active = []

    def watched(self):
        """Returns the list of watched files."""
        return self._watched

    def active(self):
        """Returns the list of active files."""
        return self.active

    def modified(self, only_active=False):
        """Returns the list of modified files."""
        return self._modified

    def update(self, only_active=False):
        """Updates the current status of watched files."""
        watched = {}
        for directory in self.dirs:
            for path in glob.glob(directory + '/**', recursive=True):
                if not os.path.isdir(path):
                    watched[path] = os.path.getmtime(path)

    def _check_modified(self):
        results = {}

        for directory in self.dirs:
            for path in glob.glob(directory + '/**', recursive=True):
                if not os.path.isdir(path):
                    results[path] = os.path.getmtime(path)

        diff = {
            key: value for key, value in results.items()
            if key not in self._watched or
            value - self._watched[key] > 0
            }
        self._watched = results

        curr = time.time()
        self._modified = {
            key: value
            for key, value in self._watched.items()
            if curr - value < self._recent_ttl
        }

        return diff

    def _check_active(self):
        modified = {}
        for path, old in self._recently_modified.items():
            new = os.path.getmtime(path)
            if new - old > 0.0:
                self._recently_modified[path] = new
                self._watched[path] = new
                modified[path] = new
        return modified


class Codegen(object):
    """Performs the main logic."""
    def __init__(self):
        self._dest = ""
        self._files = {}
        self._schemas = {}
        self._templates = {}
        self._projects = {}

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
        """Adds a schema to the internal list."""
        self._schemas[schema] = Schema(File(schema))

    def add_template(self, template):
        """Adds a template to the internal list."""
        self._templates[template] = File(template)

    def add_project(self, project):
        """Adds a template to the internal list."""
        self._projects[project] = Project(Schema(File(project)))

    def add_watched(self, directory):
        """Adds a directoryt to watch for changes."""
        self._watched_dirs.append(directory)

    def print_to_stdout(self):
        """Print compile results to stdout."""
        self._do_print = True

    def start(self):
        """Starts processing."""
        if self._projects:
            for project in self._projects.values():
                print(project)

        elif self._watched_dirs:
            raise NotImplementedError("Need to reimplement file logic.")
        else:
            self.process(self._schemas.values(), self._templates.values())

    def process(self, schemas, templates):
        """Compiles the list of templates with the list of schemas."""
        for schema in schemas:
            compiler = Compiler(schema)
            for template in templates:
                compiled = compiler.compile(template)

                if self._do_print:
                    print(compiled)


def main():
    """" The main function."""
    codegen = Codegen()

    def parse_arg(arg, val):
        """Parses the given argument and value."""
        if arg == "-w" or arg == "--watch":
            for directory in val.split(","):
                codegen.add_watched(directory)
        elif arg == "-p" or arg == "--project":
            for path in val.split(","):
                codegen.add_project(path)
        elif arg == "--print":
            codegen.print_to_stdout()

    for i, arg in enumerate(sys.argv):
        if i == 0:
            continue

        if arg[0] != "-":
            __, extension = os.path.splitext(arg)
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
