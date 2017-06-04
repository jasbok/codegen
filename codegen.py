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
import logging
import os
import re
import subprocess
import sys
import time


class Git_Helper(object):
    """Helper class to get git config information."""
    LOG = logging.getLogger("Git_Helper")

    @staticmethod
    def config(prop):
        """ Uses git config to check the value of a property."""
        result = None
        try:
            result = subprocess.check_output(["git", "config", "--get", prop])\
                .decode("utf-8").replace("\n", "")
        except subprocess.CalledProcessError as ex:
            Git_Helper.LOG.error("Failed to retrieve Git config: %s", str(ex))
        return result


class FunctionResolver(object):
    """Contains resolvable functions."""

    DATE_FUNCTIONS = {
        "now": lambda x: datetime.datetime.now().strftime(x)
    }

    GIT_FUNCTIONS = {
        "email": lambda: Git_Helper.config("user.email"),
        "name": lambda: Git_Helper.config("user.name"),
        "remote": lambda: Git_Helper.config("remote.origin.url")
    }

    PROJECT_FUNCTIONS = {
        "current": {}
    }

    STRING_FUNCTIONS = {
        "upper": lambda x: x.upper(),
        "lower": lambda x: x.lower(),
        "camel": lambda x: x.title().replace(" ", ""),
        "snake": lambda x: x.replace(" ", "_")
    }

    FUNCTIONS = {
        "date": DATE_FUNCTIONS,
        "git": GIT_FUNCTIONS,
        "project": PROJECT_FUNCTIONS,
        "str": STRING_FUNCTIONS
    }

    @staticmethod
    def resolve(path):
        """Gets the value corresponding with the path, None otherwise."""
        if isinstance(path, str):
            path = path.split(".")
        elif not isinstance(path, list):
            raise ValueError("Expected str or list:", path)

        curr_path = []
        func = FunctionResolver.FUNCTIONS
        for seg in path:
            if callable(func):
                raise ValueError("Function does not exist ('{}''). "
                                 "Did you mean '{}'"
                                 .format(".".join(path),
                                         ".".join(curr_path + seg)))
            elif not isinstance(func, dict):
                print(seg, curr_path)
                raise ValueError("Function does not exist ('{}'')."
                                 .format(".".join(path)))
            else:
                if seg in func:
                    func = func[seg]
                else:
                    alts = []
                    for key, value in func.items():
                        if callable(value):
                            alts.append(".".join(curr_path + [key]))
                    alts = ", ".join(alts)
                    raise ValueError("Function does not exist ('{}'').{}"
                                     .format(".".join(path),
                                             " Did you mean one of: " + alts
                                             if alts else ""))
            curr_path.append(seg)

        if not isinstance(func, str) and not callable(func):
            raise ValueError("Not a function or string ({})."
                             .format(".".join(curr_path)))

        return func


class Token(object):
    """Contains functionality to read and store codegen tokens."""
    R_OPERATOR = r"(\$\$|!!|\^\^|@@!|@@|%%)"
    R_PATH = r"(?:((?:\.[\w]+)*)\.{0,2})?"
    R_SELECT = r"(?:\s*\[\[(.*?)\]\])?"
    R_EXPANSION = r"(?:[ ]?{{\n?(.+?)([ ]*)}}(\n)?)?"

    REGEX_TOKEN = re.compile(
        R_OPERATOR + R_PATH + R_SELECT + R_EXPANSION, re.DOTALL | re.MULTILINE)

    def __init__(self, match):
        self.operator = match.group(1)
        self.path = match.group(2)[1:].split(".") if match.group(2) else []
        self.select = match.group(3)
        self.expansion = match.group(4)
        self.space_end = match.group(5) if match.group(5) is not None else ""
        self.eol = match.group(6) is not None
        self.indent = self._expansion_indent()
        self.start = match.start()
        self.end = match.end()

        if self.expansion is not None and self.expansion.count("\n") == 0:
            if self.eol:
                self.end -= 1
            self.expansion += self.space_end
            self.indent = 0

    def __repr__(self):
        return "Token[operator='{}', path='{}', select='{}', expansion='{}', "\
                "start='{}', end='{}']".format(self.operator, self.path,
                                               self.select, self.expansion,
                                               self.start, self.end)

    def resolve_template(self, cut_last_char=False):
        """Resolves the template from the token path."""
        template = File(os.path.join(*self.path) + ".template").read()
        if cut_last_char:
            template = template[:-1]
        return template

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

    def _expansion_indent(self):
        if self.expansion:
            indent = 0
            for c in self.expansion:
                if c == '\n':
                    indent = 0
                elif c != ' ' and c != '\t':
                    return indent
                indent += 1
            return 0

    @staticmethod
    def find(content):
        """Finds the first token in the given string."""
        match = Token.REGEX_TOKEN.search(content)
        return Token(match) if match else None


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
        self._log = logging.getLogger(self.__class__.__name__)

    def __repr__(self):
        return "File[path='{}', atime='{}', mtime='{}']".format(
            self._path, self._atime, self._mtime)

    def atime(self, no_cache=True):
        """Get the last access time."""
        if no_cache or self._atime is None:
            self._atime = None
            if not self.exists():
                self._log.warning("Could not read atime, file does not exist: "
                                  "%s", self._path)
            else:
                try:
                    self._atime = os.path.getatime(self._path)
                except OSError as ex:
                    self._logger.error("File.atime - OS exception: %s %s",
                                       self._path, ex)

        return self._atime

    def mtime(self, no_cache=True):
        """Get the last modified time."""
        if no_cache or self._mtime is None:
            self._mtime = None
            if not self.exists():
                self._log.warning("Could not read mtime, file does not exist: "
                                  "%s", self._path)
            else:
                try:
                    self._mtime = os.path.getmtime(self._path)
                except OSError as ex:
                    self._log.error("File.mtime - OS exception: %s %s",
                                    self._path, ex)

        return self._mtime

    def exists(self):
        """Checks whether file exists."""
        return os.path.isfile(self._path)

    def path(self):
        """Gets the file path."""
        return self._path

    def basename(self):
        """Returns the file basename."""
        return os.path.basename(self._path)

    def parent_dir(self):
        """Gets the parent directoy of the file."""
        return os.path.dirname(self._path)

    def read(self, no_cache=True):
        """Reads the contents of the file."""
        if no_cache and self._mtime != self.mtime() or self._contents is None:
            self._contents = None
            if not self.exists():
                self._log.warning("Could not read file, file does not exist: "
                                  "%s", self._path)
            else:
                try:
                    with open(self._path, 'r') as file:
                        self._contents = file.read()
                except FileNotFoundError as ex:
                    self._log.error("File.read - File not found: %s %s",
                                    self._path, ex)
                except IOError as ex:
                    self._log.error("File.read - IO error on load: %s %s",
                                    self._path, ex)

        return self._contents

    def touch(self):
        """Create an empty file if it doesn't exist and/or update the utime."""
        if not self.exists():
            self.write("")
        else:
            os.utime(self._path)
            self.atime()
            self.mtime()

    def write(self, contents):
        """Writes the contents to cache and disk."""
        success = False
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, 'w') as file:
                file.write(contents)
                success = True
        except IOError as ex:
            self._log.error("File.write - An IO error occurred: %s %s",
                            self._path, ex)

        self.atime()
        self.mtime()

        return success

    def empty_cache(self):
        """Empties the cache."""
        self._atime = None
        self._mtime = None
        self._contents = None


class Schema(File):
    """Contains functionality to parse and view a json schema."""
    def __init__(self, path, initialise_json=True):
        if not isinstance(path, str):
            raise ValueError("Schema() - Expected str: ", path)

        File.__init__(self, path)
        self.log = logging.getLogger(self.__class__.__name__)
        self._mtime = None
        self._json = None

    def __repr__(self):
        return "Schema[file={}]".format(self.path())

    def id(self):
        """Returns the id of the schema."""
        return self.path()

    def update(self):
        """Updates the schema if it has been modified."""
        contents = self.read()
        if contents:
            self._json = json.loads(contents)
        else:
            self.log.error("Could not load json from file: %s", self.path())
            self._json = {}

    def json(self, path=None):
        """Returns the json contained in the schema."""
        if isinstance(path, str):
            return self._json[path] if path in self._json else None
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
                    self.log.error("Segment index out of bounds (%s): %s",
                                   var, seg)
                    return None
            elif seg not in var:
                self.log.warning("Segment not found in var '%s' (%s): %s",
                                 seg, scope, var)
                return None
            var = var[seg]

        return var


class Project(Schema):
    """Contains configs to generate project files."""
    def __init__(self, path):
        if not isinstance(path, str):
            raise ValueError("Project() - Expected str:", path)

        Schema.__init__(self, path)

        self._filestore = {
            "schema": {},
            "template": {},
            "out": {}
        }
        self._recent = []
        self._owd = None
        self._updated_files = {}
        self._log = logging.getLogger(self.__class__.__name__)

    def __repr__(self):
        return "Project[path='{}']".format(self.path())

    def update(self):
        start_time = time.time()
        FunctionResolver.PROJECT_FUNCTIONS["current"]["project"] = \
            self.basename()

        super().update()
        output = self.json("output")
        if output is not None:
            self._cd_project_dir()
            self._updated_files = {}
            for i, item in enumerate(output):
                try:
                    self._process_output(item)
                except ValueError as ex:
                    self._log.error("Failed to process output item [%s] "
                                    "in project file (%s) =>\t\n%s:\t\n%s",
                                    i, self.path(), str(ex), item)
            self._cd_owd()
        self.log.info("Project (%s) compiled in %s seconds",
                      self.path(), time.time() - start_time)

    def _process_output(self, item):
        if "schema" not in item:
            raise ValueError("Malformed output item, missing schema.")
        if "template" not in item:
            raise ValueError("Malformed output item, missing template.")
        if "out" not in item:
            raise ValueError("Malformed output item, missing out.")

        schemas = glob.glob(item["schema"])
        templates = glob.glob(item["template"])
        out = item["out"]

        for schema in schemas:
            for template in templates:
                self._upsert_group(schema, template, out)

    def _upsert_group(self, schema_path, template_path, out_path):
        schema = Schema(schema_path)
        template = File(template_path)

        if not schema.exists():
            raise ValueError("Schema does not exist: %s", schema.path())
        if not template.exists():
            raise ValueError("Template does not exist: %s", template.path())

        out = File(Compiler(schema).compile(out_path))
        if not out.exists():
            out.touch()

        su = self._upsert_file("schema", schema)
        tu = self._upsert_file("template", template)
        ou = self._upsert_file("out", out)

        if su or tu or ou:
            FunctionResolver.PROJECT_FUNCTIONS["current"]["schema"] = \
                schema.path()
            FunctionResolver.PROJECT_FUNCTIONS["current"]["template"] = \
                template.path()

            compiled = Compiler(schema).compile(template)
            out.write(compiled)
            self._upsert_file("out", out, force_update=True)
        return True

    def _upsert_file(self, ftype, file, force_update=False):
        if not force_update and file.path() in self._updated_files:
            return self._updated_files[file.path()]

        updated = True
        if file.path() not in self._filestore[ftype]:
            self._filestore[ftype][file.path()] = {
                "file": file,
                "mtime": file.mtime()
            }
        else:
            mtime = file.mtime()
            if self._filestore[ftype][file.path()]["mtime"] < mtime:
                self._filestore[ftype][file.path()]["mtime"] = mtime
            else:
                updated = False

        self._updated_files[file.path()] = updated
        return updated

    def _cd_project_dir(self):
        self._owd = os.getcwd()
        os.chdir(self.parent_dir())

    def _cd_owd(self):
        if self._owd is not None:
            os.chdir(self._owd)
            self._owd = None


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

    def curr_scope(self):
        """Returns the current scope"""
        return self._scopes[-1] if self._scopes else None

    def schema_path(self):
        """Returns the path of the held schema."""
        return self._schema.path()


class Compiler(object):
    """Builds a template compiler from a given schema."""

    def __init__(self, schema):
        if not isinstance(schema, Schema):
            raise ValueError(
                "Compiler() - Expected Schema: ", schema)

        self.log = logging.getLogger(self.__class__.__name__)
        self._stack = Schema_Stack(schema)
        schema.update()

    def compile(self, template):
        """Compiles a template using the compiler schema."""
        if isinstance(template, File):
            tmp = template.read()
        elif isinstance(template, str):
            tmp = template
        else:
            raise TypeError("Expected str or File: ", template)

        if not tmp:
            raise ValueError("Could not compile: Empty template.")

        out = ""
        token = Token.find(tmp)
        while token is not None:
            out += tmp[:token.start]
            resolved = self._resolve(token)

            if token.expansion:
                indent = token.indent - Compiler.curr_line_length(out)
                if indent != 0:
                    ind = "\n" + " " * abs(indent)
                    if indent > 0:
                        resolved = resolved.replace(ind, "\n")[token.indent:]
                    else:
                        resolved = resolved.replace("\n", ind)

            tmp = resolved + tmp[token.end:]
            token = Token.find(tmp)

        return out + tmp

    @staticmethod
    def curr_line_length(string):
        """Gets the length of the last line."""
        indent = 0
        for c in reversed(string):
            if c == '\n':
                return indent
            indent += 1
        return 0

    def _resolve(self, token):
        op = token.operator

        if op == "$$" or op == "!!" or op == "^^":
            result = self._resolve_value(token)
        elif op == "%%":
            func = FunctionResolver.resolve(token.path)
            if func:
                if isinstance(func, str):
                    result = func
                elif callable(func):
                    if token.expansion:
                        result = func(self.compile(token.expansion))
                    else:
                        result = func()
                else:
                    raise ValueError("Resolved is not a function or a string "
                                     "({} => {}).".format(".".join(token.path),
                                                          func))

        elif op == "@@" or op == "@@!":
            result = token.resolve_template(op == "@@!")

        return result or ""

    def _resolve_value(self, token):
        if not isinstance(token, Token):
            raise TypeError("Expected Token: ", token)

        resolved = ""
        self._stack.push(token)
        var = self._stack.value()
        if var is not None:
            if token.expansion is not None:
                if isinstance(var, list):
                    for index in token.resolve_indices(var):
                        self._stack.push(index)
                        resolved += self.compile(token.expansion)
                        self._stack.pop()
                else:
                    select = token.select
                    do_compile = select is None \
                        or isinstance(var, bool) and var == bool(select) \
                        or isinstance(var, int) and var == int(select) \
                        or isinstance(var, float) and var == float(select) \
                        or isinstance(var, str) and var == select
                    if do_compile:
                        resolved = self.compile(token.expansion)
            else:
                resolved = str(var)
        else:
            self.log.warning("Schema variable is null: %s [%s]",
                             self._stack.curr_scope(),
                             self._stack.schema_path())
        self._stack.pop()

        return resolved


class Codegen(object):
    """Performs the main logic."""
    def __init__(self):
        self._schemas = {}
        self._templates = {}
        self._projects = {}

        self._do_print = False
        self._do_watch = False

        self._watch_interval = 15
        self._recent_interval = 2
        self._recent_ttl = 300
        self._watch_interval_counter = 0

    def add_schema(self, schema):
        """Adds a schema to the internal list."""
        self._schemas[schema] = Schema(schema)

    def add_template(self, template):
        """Adds a template to the internal list."""
        self._templates[template] = File(template)

    def add_project(self, project):
        """Adds a template to the internal list."""
        self._projects[project] = Project(project)

    def watch_project(self):
        """Print compile results to stdout."""
        self._do_watch = True

    def print_to_stdout(self):
        """Print compile results to stdout."""
        self._do_print = True

    def start(self):
        """Starts processing."""
        if self._projects:
            while True:
                for project in self._projects.values():
                    project.update()
                if not self._do_watch:
                    break
                try:
                    time.sleep(2)
                except KeyboardInterrupt:
                    break
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

    msg_format = "[%(levelname)s] %(asctime)s "                             \
                 "(%(filename)s:%(lineno)d -> %(name)s::%(funcName)s): "    \
                 "%(message)s"
    date_format = "%Y-%m-%dT%H:%M:%S"
    logging.basicConfig(level=logging.DEBUG,
                        format=msg_format,
                        datefmt=date_format)

    def parse_arg(arg, val):
        """Parses the given argument and value."""
        if arg == "-p" or arg == "--project":
            for path in val.split(","):
                codegen.add_project(path)
        if arg == "-w" or arg == "--watch":
            codegen.watch_project()
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
