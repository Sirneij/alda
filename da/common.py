# Copyright (c) 2010-2017 Bo Lin
# Copyright (c) 2010-2017 Yanhong Annie Liu
# Copyright (c) 2010-2017 Stony Brook University
# Copyright (c) 2010-2017 The Research Foundation of SUNY
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import sys
import copy
import time
import pickle
import os.path
import logging
import warnings
import threading

from datetime import datetime
from collections import abc, deque, namedtuple
from inspect import signature
from inspect import Parameter
from functools import wraps

MAJOR_VERSION = 1
MINOR_VERSION = 1
PATCH_VERSION = 2
PRERELEASE_VERSION = "rc16"

__version__ = "{}.{}.{}{}".format(MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION,
                                   PRERELEASE_VERSION)

INCOQ_MODULE_NAME = "incoq.mars.runtime"

# a dict that contains the runtime configuration values:
GlobalOptions = None
# a dict containing configuration overrides set by the `config` API:
GlobalConfig = dict()
# Process id of the node process:
CurrentNode = None
# incoq.runtime.Type, only if using incoq:
IncOQBaseType = None
# all loaded DistAlgo modules, corresponds to sys.modules:
modules = dict()

CONSOLE_LOG_FORMAT = \
    '[%(relativeCreated)d] %(name)s<%(processName)s>:%(levelname)s: %(message)s'
FILE_LOG_FORMAT = \
    '[%(asctime)s] %(name)s<%(processName)s>:%(levelname)s: %(message)s'

# Define custom levels for text output from user code using the `output`,
# `debug`, and `error` builtins, to differentiate output from user programs and
# log messages from the DistAlgo system:
logging.addLevelName(logging.INFO+1, "OUTPUT")
logging.addLevelName(logging.INFO+2, "USRERR")
logging.addLevelName(logging.DEBUG+1, "USRDBG")

log = logging.getLogger(__name__)

api_registry = dict()
builtin_registry = dict()
internal_registry = dict()

class InvalidStateException(RuntimeError): pass

class ConfigurationError(RuntimeError): pass
    
def get_runtime_option(key, default=None):
    """Returns the configured value of runtime option 'key', or 'default' if 'key'
    is not configured.

    """
    if GlobalOptions is None:
        if default is None:
            raise InvalidStateException("DistAlgo is not initialized.")
        else:
            return default

    return GlobalOptions.get(key, default)

def set_runtime_option(key, value):
    if GlobalOptions is None:
        raise InvalidStateException("DistAlgo is not initialized.")

    GlobalOptions[key] = value

def _version_as_bytes():
    """Return a 4-byte representation of the version number.
    """
    prerelease = sum(ord(c) for c in PRERELEASE_VERSION) % 256
    return (((MAJOR_VERSION & 0xff) << 24) | ((MINOR_VERSION & 0xff) << 16) |
            ((PATCH_VERSION & 0xff) << 8) | prerelease).to_bytes(4, 'big')
VERSION_BYTES = _version_as_bytes()

def _parse_items(items):
    subs = dict()
    if items:
        for item in items:
            parts = item.split(':')
            if len(parts) != 2:
                raise InvalidStateException('unrecognized substitute spec: {}'
                                            .format(item))
            subs[parts[0]] = parts[1]
    return subs

def _set_hostname():
    """Sets a canonical hostname for this process.

    The "hostname" global option serves three distinct purposes within DistAlgo:
    1) it determines the network interface(s) on which DistAlgo listens for
    incoming messages; 2) it is a component of the globally unique `ProcessId`
    used to identify DistAlgo processes; 3) during message routing, the
    "hostname" component of the target `ProcessId` is used to determine the
    proper forwarding path. Therefore, we must ensure that all DistAlgo
    processes in a distributed network use the same hostname string for each
    physical host in the network, or else message loss may occur.

    """
    import socket

    hostname = GlobalOptions.get('hostname')
    if hostname is None:
        if len(GlobalOptions['nodename']) > 0:
            hostname = socket.getfqdn()
        else:
            hostname = 'localhost'

    try:
        GlobalOptions['hostname'] = socket.gethostbyname(hostname)
    except socket.error as e:
        if GlobalOptions.get('hostname') is None:
            msg = (f'This system is configured to use "{hostname}" as its fully '
                   'qualified domain name, but it is not resolvable. Please '
                   'specify a hostname or an IP address via the "--hostname"'
                   '(or equivalently "-H") command line argument. If you only '
                   'intend to connect to other DistAlgo nodes running on '
                   'this system, you can use "-H localhost". Otherwise, '
                   'you must specify a hostname or an IP address that is '
                   'reachable from remote hosts.')
        else:
            msg = f'"{hostname}" is not a resolvable hostname.'
        raise ConfigurationError(msg) from e


def initialize_runtime_options(options=None):
    """Sets and sanitizes runtime options.

    'options' should be a dict-like object containing mappings from options
    names to corresponding values.

    """
    import multiprocessing

    from . import compiler

    global GlobalOptions

    if not GlobalOptions:
        GlobalOptions = dict()
    if options:
        GlobalOptions.update(options)
    # Parse '--substitute-classes' and '--substitute-modules':
    GlobalOptions['substitute_classes'] = \
                            _parse_items(GlobalOptions.get('substitute_classes'))
    GlobalOptions['substitute_modules'] = \
                            _parse_items(GlobalOptions.get('substitute_modules'))

    if GlobalOptions.get('nodename') is None:
        GlobalOptions['nodename'] = ''

    _set_hostname()

    # Configure multiprocessing package to use chosen semantics:
    startmeth = GlobalOptions.get('start_method')
    if startmeth != multiprocessing.get_start_method(allow_none=True):
        multiprocessing.set_start_method(startmeth)

    # Convert 'compiler_flags' to a namespace object that can be passed directly
    # to the compiler:
    GlobalOptions['compiler_args'] \
        = compiler.ui.parse_compiler_args(
            GlobalOptions.get('compiler_flags', '').split())

    # Make sure the directory for storing trace files exists:
    if GlobalOptions.get('record_trace'):
        if 'logdir' not in GlobalOptions:
            raise ConfigurationError(
                "'record_trace' enabled without setting 'logdir'")
        os.makedirs(GlobalOptions['logdir'], exist_ok=True)

def set_global_config(props):
    GlobalConfig.update(props)

def global_config():
    return GlobalConfig

def _set_node(node_id):
    global CurrentNode
    CurrentNode = node_id

def pid_of_node():
    return CurrentNode

def get_inc_module():
    if GlobalOptions is None:
        raise InvalidStateException("DistAlgo is not initialized.")
    if not hasattr(sys.modules, GlobalOptions['inc_module_name']):
        return None
    return sys.modules[GlobalOptions['inc_module_name']]

def add_da_module(module):
    """Register 'module' as a DistAlgo module.

    This method is intended to be called from the importer module.

    """
    modules[module.__name__] = module
    setup_logging_for_module(module.__name__)

def sysinit():
    """Initialize the DistAlgo system.

    This function must be called before any DistAlgo code can run. Specifically,
    every child process created under spawning semantics must call this function
    during initialization.

    """
    # Set the format used to convert ProcessId to its string representation:
    pid_format = GlobalOptions['pid_format']
    if pid_format == 'full':
        ProcessId.__str__ = ProcessId.__repr__ = ProcessId._full_form_
    elif pid_format == 'long':
        ProcessId.__str__ = ProcessId.__repr__ = ProcessId._long_form_
    else:
        # default is short
        pass
    # Setup system logging:
    setup_logging_for_module('da', CONSOLE_LOG_FORMAT, FILE_LOG_FORMAT)

def global_init(config):
    """Convenience method for one-time system setup.

    This function should be called once for each node. The Python process that
    called this function then becomes a DistAlgo node process.

    """
    initialize_runtime_options(config)
    sysinit()

DA_MODULE_CONSOLE_FORMAT = \
    '[%(relativeCreated)d] %(name)s%(daPid)s:%(levelname)s: %(message)s'
DA_MODULE_FILE_FORMAT = \
    '[%(asctime)s] %(name)s%(daPid)s:%(levelname)s: %(message)s'
def setup_logging_for_module(modulename,
                             consolefmt=DA_MODULE_CONSOLE_FORMAT,
                             filefmt=DA_MODULE_FILE_FORMAT):
    """Configures package level logger.

    """
    if GlobalOptions is None:
        # We're not yet initialized, which will happen when using `import_da`
        # under spawning semantics. This is fine, as logging will be setup after
        # `OSProcessContainer.run` gets called. We can safely ignore this call:
        return
    rootlog = logging.getLogger(modulename)
    rootlog.handlers = []       # Clear all handlers

    if not GlobalOptions['no_log']:
        rootlog.propagate = False
        rootlog.setLevel(logging.DEBUG)
        consoleformatter = logging.Formatter(consolefmt)
        consolelvl = logging._nameToLevel[GlobalOptions['logconsolelevel'].upper()]
        ch = logging.StreamHandler()
        ch.setFormatter(consoleformatter)
        ch.setLevel(consolelvl)
        rootlog._consolelvl = consolelvl
        rootlog.addHandler(ch)

        if GlobalOptions['logfile']:
            filelvl = logging._nameToLevel[GlobalOptions['logfilelevel'].upper()]
            logfilename = GlobalOptions['logfilename']
            if logfilename is None:
                if GlobalOptions['file'] is not None:
                    logfilename = os.path.basename(GlobalOptions['file'])
                elif GlobalOptions['module'] is not None:
                    logfilename = GlobalOptions['module'][0]
                else:
                    logfilename = datetime.now().strftime('%Y-%m-%d_%H%M%S')
                logfilename += '.log'
            fh = logging.FileHandler(logfilename)
            formatter = logging.Formatter(filefmt)
            fh.setFormatter(formatter)
            fh.setLevel(filelvl)
            rootlog._filelvl = filelvl
            rootlog.addHandler(fh)
    else:
        rootlog.addHandler(logging.NullHandler())

def load_modules():
    import importlib
    global IncOQBaseType
    if not GlobalOptions['load_inc_module']:
        return
    main = sys.modules[GlobalOptions['this_module_name']]
    inc = importlib.import_module(GlobalOptions['inc_module_name'])
    if inc.JbStyle:
        IncOQBaseType = importlib.import_module(INCOQ_MODULE_NAME) \
                        .IncOQType
    if GlobalOptions['control_module_name'] is not None:
        ctrl = importlib.import_module(GlobalOptions['control_module_name'])
        main.IncModule = ModuleIntrument(ctrl, inc)
    else:
        main.IncModule = inc

####################
# Process ID
####################
ILLEGAL_NAME_CHARS = set('@#:')

def check_name(name):
    return not (set(name) & ILLEGAL_NAME_CHARS)

def name_split_host(name):
    """Splits `name` into 'processname', 'hostname', and 'port' components."""
    comps = name.split('@')
    if len(comps) == 2:
        name, suffix = comps
        suffix = suffix.split(':')
        if len(suffix) > 2:
            return (None, None, None)
        elif len(suffix) == 2:
            host, port = suffix
            try:
                return (name, host, int(port))
            except ValueError:
                return (None, None, None)
        elif len(suffix) == 1:
            return (name, suffix[0], None)
        else:
            return (name, None, None)
    elif len(comps) == 1:
        return (comps[0], None, None)
    else:
        return (None, None, None)

def name_split_node(name):
    """Splits `name` into 'processname', 'nodename' components."""
    assert '@' not in name
    comps = name.split('#')
    if len(comps) == 2:
        return tuple(comps)
    elif len(comps) == 1:
        return (comps[0], comps[0])
    else:
        return (None, None)

#########################
# Custom pickling

class _ObjectLoader(pickle.Unpickler):
    """Unpickler that honors the '--substitute_classes' command line option."""

    def __init__(self, file, **rest):
        super().__init__(file, **rest)
        if GlobalOptions['substitute_classes'] or \
           GlobalOptions['substitute_modules']:
            self.find_class = self._find_class

    def _find_class(self, module, name):
        module = GlobalOptions['substitute_modules'].get(module, module)
        name = GlobalOptions['substitute_classes'].get(name, name)
        return super().find_class(module, name)

def _loads(buf):
    file = io.BytesIO(buf)
    return _ObjectLoader(file).load()

# default to the standard library if we don't need to do anything wacky:
ObjectLoader = _ObjectLoader
ObjectDumper = pickle.Pickler
loads = pickle.loads
dumps = pickle.dumps

#####################
# Process Id

class ProcessId(namedtuple("_ProcessId",
                           'uid, seqno, pcls, \
                           name, nodename, hostname, transports')):
    """An instance of `ProcessId` uniquely identifies a DistAlgo process instance.

    A `ProcessId` instance should contain all necessary information for any
    DistAlgo process in a distributed system to send messages to that process.
    This includes the network addresses of all ports the process listens on.

    There is a total ordering over the set of all `ProcessId`s. `ProcessId`s
    referring to the same process will always compare equal.

    From the point of view of DistAlgo programs, `ProcessId` instances are
    opaque objects -- no assumptions should be made about the internal structure
    of `ProcessId` instances.

    """
    __slots__ = ()
    _pid_counter = 0
    _lock = threading.Lock()
    _named = dict()
    _callbacks = dict()

    def __new__(cls, uid, seqno, pcls, name, nodename, hostname, transports):
        obj = super().__new__(cls, uid, seqno, pcls, name, nodename, hostname,
                              transports)
        if len(name) > 0:
            fullname = (name, nodename)
            with ProcessId._lock:
                entry = ProcessId._named.get(fullname, None)
                callbacks = ProcessId._callbacks.get(fullname, None)
                if isinstance(entry, ProcessId):
                    if obj < entry:
                        # cached id is more recent than the new one, so use the
                        # cached entry:
                        obj = entry
                    elif obj.uid != entry.uid:
                        log.warning("Process name '%s#%s' reassigned from %s "
                                    "to %s.", name, nodename,
                                    ProcessId._full_form_(entry),
                                    ProcessId._full_form_(obj))
                if entry != obj:
                    ProcessId._named[fullname] = obj
                if callbacks is not None:
                    del ProcessId._callbacks[fullname]
            if type(callbacks) is list:
                for callback in callbacks:
                    assert callable(callback)
                    callback(obj)
        return obj

    @staticmethod
    def lookup(name):
        return ProcessId._named.get(name, None)

    @staticmethod
    def lookup_or_register_callback(name, callback):
        with ProcessId._lock:
            if name not in ProcessId._named:
                if name not in ProcessId._callbacks:
                    ProcessId._callbacks[name] = [callback]
                else:
                    ProcessId._callbacks[name].append(callback)
                return None
            else:
                return ProcessId._named[name]

    @staticmethod
    def all_named_ids():
        with ProcessId._lock:
            return list(ProcessId._named.values())

    @staticmethod
    def drop_entry(nid):
        with ProcessId._lock:
            if nid.name in ProcessId._named:
                del ProcessId._named[nid.name]

    @staticmethod
    def gen_uid(hostname, pid):
        """Generate a globally unique 96-bit id.

        """
        # 54 bits of timestamp:
        tstamp = int(time.time() * 1000) & 0x3fffffffffffff
        # 16 bits of hostname hash
        hh = int(hash(hostname)) & 0xffff
        # 16 bits of os pid
        pid %= 0xffff
        # 10 bit global counter
        with ProcessId._lock:
            cnt = ProcessId._pid_counter = (ProcessId._pid_counter + 1) % 1024
        return (tstamp << 42) | (hh << 26) | (pid << 10) | cnt

    @classmethod
    def _create(idcls, pcls, transports, name=""):
        """Creates a new `ProcessId` instance.

        """
        hostname = get_runtime_option('hostname')
        nodename = get_runtime_option('nodename')
        uid = ProcessId.gen_uid(hostname,
                                pid=threading.current_thread().ident)
        return idcls(uid=uid, seqno=1, pcls=pcls,
                     name=name, nodename=nodename,
                     hostname=hostname, transports=transports)

    def address_for_transport(self, transport):
        """Returns the address corresponding to `transport`.

        """
        if len(self.transports) <= transport.slot_index:
            return None
        addr = self.transports[transport.slot_index]
        if addr is None:
            return None
        else:
            return (self.hostname, addr)

    def _filename_form_(self):
        """Constructs a filesystem-friendly representation of this pid.

        This form is designed to be use as filenames for logs, traces, etc.

        """
        if len(self.nodename) > 0 and self.nodename != self.name:
            if len(self.name) > 0:
                return "{0.pcls.__name__}-{0.name}.{0.nodename}".format(self)
            else:
                return "{0.pcls.__name__}-{1:x}.{0.nodename}".format(self, self.uid)
        else:
            if len(self.name) > 0:
                return "{0.pcls.__name__}-{0.name}".format(self)
            else:
                return "{0.pcls.__name__}-{1:x}".format(self, self.uid)

    def _short_form_(self):
        """Constructs a short string representation of this pid.

        This form is more suitable for use in output strings.

        """
        if len(self.nodename) > 0 and self.nodename != self.name:
            if len(self.name) > 0:
                return "<{0.pcls.__name__}:{0.name}#{0.nodename}>".format(self)
            else:
                # otherwise, we use `uid` truncated to the last 5 hex digits:
                return "<{0.pcls.__name__}:{1:05x}#{0.nodename}>".format(
                    self, self.uid & 0xfffff)
        else:
            if len(self.name) > 0:
                return "<{0.pcls.__name__}:{0.name}>".format(self)
            else:
                return "<{0.pcls.__name__}:{1:05x}>".format(self, self.uid & 0xfffff)

    def _long_form_(self):
        """Constructs a short string representation of this pid.

        This form is more suitable for use in output strings.

        """
        if len(self.nodename) > 0 and self.nodename != self.name:
            if len(self.name) > 0:
                return "<{0.pcls.__name__}:{0.name}#{0.nodename}>".format(self)
            else:
                # otherwise, we use the full hex representation of `uid`:
                return "<{0.pcls.__name__}:{1:x}#{0.nodename}>".format(self, self.uid)
        else:
            if len(self.name) > 0:
                return "<{0.pcls.__name__}:{0.name}>".format(self)
            else:
                return "<{0.pcls.__name__}:{1:x}>".format(self, self.uid)

    def _full_form_(self):
        """Constructs a full string representation of this pid.

        This form may be more useful in debugging.

        """
        fmt = "ProcessId(uid={0.uid:x}, seqno={0.seqno}, " \
              "pcls={0.pcls.__name__}, " \
              "name='{0.name}', nodename='{0.nodename}', " \
              "hostname='{0.hostname}', transports={0.transports})"
        return fmt.format(self)

    __str__ = __repr__ = _short_form_

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

####################

warnings.simplefilter("default", DeprecationWarning)
def deprecated(func):
    """Declare 'func' as deprecated.

    This is a decorator which can be used to mark functions as deprecated. It
    will result in a warning being emmitted when the function is used.

    """
    def newFunc(*args, **kwargs):
        warnings.warn("Call to deprecated function %s." % func.__name__,
                      category=DeprecationWarning, stacklevel=2)
        return func(*args, **kwargs)
    newFunc.__name__ = func.__name__
    newFunc.__doc__ = func.__doc__
    newFunc.__dict__.update(func.__dict__)
    return newFunc

def api(func):
    """Declare 'func' as DistPy API.

    This wraps the function to perform basic type checking for type-annotated
    parameters and return value.

    """
    global api_registry
    funame = func.__name__
    if api_registry.get(funame) is not None:
        return api_registry[funame]

    sig = signature(func)

    @wraps(func)
    def _func_impl(*args, **kwargs):
        try:
            binding = sig.bind(*args, **kwargs)
        except TypeError as e:
            log.error(str(e))
            return None
        for argname in binding.arguments:
            atype = sig.parameters[argname].annotation
            if (atype is not Parameter.empty and
                    not isinstance(binding.arguments[argname], atype)):
                log.error(
                    "'%s' called with wrong type argument: "
                     "%s, expected %s, got %s.",
                    funame, argname, str(atype),
                    str(binding.arguments[argname].__class__))
                return None
        result = func(*args, **kwargs)
        if (sig.return_annotation is not Parameter.empty and
                not isinstance(result, sig.return_annotation)):
            log.warning(
                "Possible bug: API function '%s' return value type mismatch: "
                "declared %s, returned %s.",
                funame, sig.return_annotation, result.__class__)
        return result

    _func_impl.__name__ = func.__name__
    _func_impl.__doc__ = func.__doc__
    _func_impl.__dict__.update(func.__dict__)
    api_registry[funame] = _func_impl
    return _func_impl

def builtin(func):
    """Declare `func` as DistAlgo builtin.

    Builtins are instance methods of da.DistProcess, and must be called with
    the process instance as first argument (self).

    """
    funame = func.__name__
    if builtin_registry.get(funame) is not None:
        return builtin_registry[funame]
    else:
        builtin_registry[funame] = func
        return func

def internal(func):
    """Declare `func` as `DistProcess` internal implementation.

    This gives the compiler a hint to prevent user code from unintentionally
    overriding an internal function.

    """
    funame = func.__name__
    internal_registry[funame] = func
    return func

class Namespace(object):
    pass

class Null(object):
    def __init__(self, *args, **kwargs): pass
    def __call__(self, *args, **kwargs): return self
    def __getattribute__(self, attr): return self
    def __setattr__(self, attr, value): pass
    def __delattr__(self, attr): pass

class BufferIOWrapper:
    def __init__(self, barray):
        self.buffer = barray
        self.total_bytes = len(barray)
        self.fptr = 0

    def write(self, data):
        end = self.fptr + len(data)
        if end > self.total_bytes:
            raise IOError("buffer full.")
        self.buffer[self.fptr:end] = data
        self.fptr = end

class QueueEmpty(Exception): pass
class WaitableQueue:
    """This class implements a fast waitable queue based on a `deque`.

    The `Queue` class from the standard library `queue` module has a lot of
    unneccesary overhead due to synchronization on every `get` and `put`
    operation. We can avoid these synchronization overheads by piggy-backing off
    the CPython GIL when the queue is non-empty.

    """
    def __init__(self, iterable=[], maxlen=None, trace_files=None):
        self._q = deque(iterable, maxlen)
        self._condition = threading.Condition()
        self._num_waiting = 0
        if trace_files is not None:
            self._in_file, self._out_file = trace_files
            self._in_dumper = ObjectDumper(self._in_file)
            self._out_dumper = ObjectDumper(self._out_file)
            self.__pop = self.pop
            self.pop = self._pop_and_record
        else:
            self._in_file = self._out_file = None

    def append(self, item):
        self._q.append(item)
        if self._num_waiting > 0:
            with self._condition:
                self._condition.notify_all()

    def close(self):
        if self._in_file is not None:
            self._in_file.close()
            self._in_file = None
        if self._out_file is not None:
            self._out_file.close()
            self._out_file = None

    def pop(self, block=True, timeout=None):
        # Opportunistically try to get the next item off the queue:
        try:
            return self._q.popleft()
        except IndexError:
            pass
        # The queue was empty, if we don't need to block then we're done:
        if not block or timeout == 0:
            raise QueueEmpty()
        # Otherwise, we have to acquire the condition object and block:
        try:
            with self._condition:
                self._num_waiting += 1
                self._condition.wait(timeout)
                self._num_waiting -= 1
            return self._q.popleft()
        except IndexError:
            # If the queue is still empty at this point, it means that the new
            # event was picked up by another thread, so it's ok for us to
            # return:
            raise QueueEmpty()
        # Other exceptions will be propagated

    def _pop_and_record(self, block=True, timeout=None):
        """Version of `pop` that records a trace of queue items.

        """
        if block and timeout:
            delay = time.time()
        else:
            delay = None
        try:
            item = self.__pop(block, timeout)
            if delay:
                delay = time.time() - delay
            self._in_dumper.dump((delay, item))
            return item
        except QueueEmpty as e:
            # We must record all `QueueEmpty` events as well, in order for the
            # execution to be fully reproduced:
            if delay:
                delay = time.time() - delay
            self._in_dumper.dump((delay, e))
            raise e

    def __len__(self):
        return self._q.__len__()

class ReplayQueue:
    """A queue that simply replays recorded messages in order.

    """
    def __init__(self, in_stream, out_stream):
        self._in_file = in_stream
        self._out_file = out_stream
        self._in_loader = ObjectLoader(in_stream)
        self._out_loader = ObjectLoader(out_stream)

    def pop(self, block=True, timeout=None):
        try:
            delay, item = self._in_loader.load()
            if delay:
                time.sleep(delay)
            if isinstance(item, common.QueueEmpty):
                raise item
            else:
                return item
        except (EOFError, pickle.UnpicklingError) as e:
            self.close()
            raise TraceEndedException("No more items in receive trace.") from e

    def close(self):
        if self._in_file is not None:
            self._in_file.close()
            self._in_file = None
        if self._out_file is not None:
            self._out_file.close()
            self._out_file = None


#########################
# LRU queue:

class Node(object):
    __slots__ = ['prev', 'next', 'me']
    def __init__(self, prev, me):
        self.prev = prev
        self.me = me
        self.next = None
    def __str__(self):
        return str(self.me)
    def __repr__(self):
        return self.me.__repr__()

class LRU:
    """
    Implementation of a length-limited O(1) LRU queue.
    Built for and used by PyPE:
    http://pype.sourceforge.net
    Copyright 2003 Josiah Carlson.
    """
    def __init__(self, count, pairs=[]):
        self.count = max(count, 1)
        self.d = {}
        self.first = None
        self.last = None
        for key, value in pairs:
            self[key] = value
    def __contains__(self, obj):
        return obj in self.d
    def __getitem__(self, obj):
        a = self.d[obj].me
        self[a[0]] = a[1]
        return a[1]
    def __setitem__(self, obj, val):
        if obj in self.d:
            del self[obj]
        nobj = Node(self.last, (obj, val))
        if self.first is None:
            self.first = nobj
        if self.last:
            self.last.next = nobj
        self.last = nobj
        self.d[obj] = nobj
        if len(self.d) > self.count:
            if self.first == self.last:
                self.first = None
                self.last = None
                return
            a = self.first
            a.next.prev = None
            self.first = a.next
            a.next = None
            del self.d[a.me[0]]
            del a
    def __delitem__(self, obj):
        nobj = self.d[obj]
        if nobj.prev:
            nobj.prev.next = nobj.next
        else:
            self.first = nobj.next
        if nobj.next:
            nobj.next.prev = nobj.prev
        else:
            self.last = nobj.prev
        del self.d[obj]
    def __iter__(self):
        cur = self.first
        while cur != None:
            cur2 = cur.next
            yield cur.me[1]
            cur = cur2
    def __str__(self):
        return str(self.d)
    def __repr__(self):
        return self.d.__repr__()
    def iteritems(self):
        cur = self.first
        while cur != None:
            cur2 = cur.next
            yield cur.me
            cur = cur2
    def iterkeys(self):
        return iter(self.d)
    def itervalues(self):
        for i,j in self.iteritems():
            yield j
    def keys(self):
        return self.d.keys()
    def get(self, k, d=None):
        v = self.d.get(k)
        if v is None: return None
        a = v.me
        self[a[0]] = a[1]
        return a[1]


class IntrumentationError(Exception): pass
class FunctionInstrument(object):
    def __init__(self, control_func, subject_func):
        super().__setattr__('_control', control_func)
        super().__setattr__('_subject', subject_func)

    def __call__(self, *args, **kwargs):
        ctrl_result = self._control(*args, **kwargs)
        subj_result = self._subject(*args, **kwargs)
        if ctrl_result != subj_result:
            raise IntrumentationError("Result mismatch for %s: "
                                      "control returned %s; "
                                      "subject returned %s." %
                                      (self._control.__name__,
                                       str(ctrl_result),
                                       str(subj_result)))
        return subj_result

    def __setattr__(self, attr, value):
        super().__setattr__(attr, value)
        setattr(self._control, attr, value)
        setattr(self._subject, attr, value)

    def __delattr__(self, attr):
        super().__delattr__(attr)
        delattr(self._control, attr)
        delattr(self._subject, attr)

class ModuleIntrument(object):
    def __init__(self, control, subject):
        super().__setattr__('_control', control)
        super().__setattr__('_subject', subject)

    def __getattribute__(self, attr):
        ctrl_attr = getattr(super().__getattribute__('_control'), attr)
        subj_attr = getattr(super().__getattribute__('_subject'), attr)
        if type(ctrl_attr) is not type(subj_attr):
            raise IntrumentationError("Attribute mismatch for %s:"
                                      "control is type %s; "
                                      "subject is type %s." %
                                      (attr, str(type(ctrl_attr)),
                                       str(type(subj_attr))))
        if hasattr(ctrl_attr, '__call__') and \
           (ctrl_attr.__name__.startswith("Query_") or
            ctrl_attr.__name__ == "init"):
                return FunctionInstrument(ctrl_attr, subj_attr)
        else:
            return subj_attr

    def __setattr__(self, attr, value):
        super().__setattr__(attr, value)
        setattr(self._control, attr, value)
        setattr(self._subject, attr, value)

    def __delattr__(self, attr):
        super().__delattr__(attr)
        delattr(self._control, attr)
        delattr(self._subject, attr)


def _install():
    """Hooks into `multiprocessing.spawn` so that GlobalOptions is propagated to
    child processes *before* they attempt to load any DistAlgo modules.

    """
    import multiprocessing.spawn

    spawn_prepare = multiprocessing.spawn.prepare
    spawn_get_preparation_data = multiprocessing.spawn.get_preparation_data
    spawn_get_command_line = multiprocessing.spawn.get_command_line

    def _advised_prepare(data):
        global GlobalOptions
        global GlobalConfig

        if 'global_options' in data:
            GlobalOptions = data['global_options']

        if 'global_config' in data:
            GlobalConfig = data['global_config']

        return spawn_prepare(data)

    def _advised_get_preparation_data(name):
        d = spawn_get_preparation_data(name)
        d['global_options'] = GlobalOptions
        d['global_config'] = GlobalConfig
        return d

    def _advised_get_command_line(**kwds):
        cmd = spawn_get_command_line(**kwds)
        for i in range(len(cmd)):
            if cmd[i] == '-c':
                break
        if i == len(cmd):
            raise RuntimeError('Unsupported Python version!!!')
        cmd[i+1] = 'import da; ' + cmd[i+1]
        return cmd

    multiprocessing.spawn.prepare = _advised_prepare
    multiprocessing.spawn.get_preparation_data = _advised_get_preparation_data
    multiprocessing.spawn.get_command_line = _advised_get_command_line

if __name__ == "__main__":
    @api
    def testapi(a : int, b : list) -> dict:
        print (a, b)
        return []

    testapi(1, [2])
    testapi(1, {})
    print(api_registry)

    @deprecated
    def testdepre():
        print("deprecated function")

    testdepre()
