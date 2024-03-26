from __future__ import annotations

import functools
import os
import re
import select
import shutil
import subprocess
import sys
import time
import unicodedata
from abc import abstractmethod
from collections.abc import Sequence, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial, wraps, lru_cache
from stat import S_ISFIFO
from types import TracebackType
from typing import Any, Callable, TextIO, Type, TypeVar, final, overload
from weakref import WeakSet

from term_app_pack.utils import Ctrl

# BLACK MAGIC, DO NOT TOUCH
# jk


_FuncT = TypeVar('_FuncT', bound=Callable)


@dataclass(frozen=True)
class _XtermAppConfig:
  alternate_buffer: bool = False
  alternate_scroll: bool = False
  hide_cursor: bool = False
  scrolling_region: tuple[int, int] | None = None
  meta_key: bool = False
  alt_numlock: bool = False
  smooth_scroll: bool = True
  fast_scroll: bool = False
  auto_wrap: bool = True
  sgr_mouse: bool = False
  utf8_mouse: bool = False
  urxvt_mouse: bool = False
  mouse_events: bool = False
  # target: io.TextIOWrapper


class XTermApplication(AbstractContextManager):
  # __slots__ = []
  # contextmethod = _contextmethod
  _recorder: TermInReader
  _in_app: bool
  _config: _XtermAppConfig
  _target: TextIO
  _safe_exceptions: tuple[type[BaseException], ...]

  @overload
  def __init__(self,
               *,
               alternate_buffer: bool = False,
               alternate_scroll: bool = False,
               hide_cursor: bool = False,
               scrolling_region: tuple[int, int] | None = None,
               meta_key: bool = False,
               alt_numlock: bool = False,
               smooth_scroll: bool = True,
               fast_scroll: bool = False,
               auto_wrap: bool = True,
               sgr_mouse: bool = False,
               utf8_mouse: bool = False,
               urxvt_mouse: bool = False,
               mouse_events: bool = False,
               recorder_hooks: Sequence[Callable[[str], Any]] = (),
               safe_exceptions: tuple[type[BaseException], ...] = (KeyboardInterrupt, SystemExit),
               target: TextIO = sys.stdout):
    ...

  def __init__(
      self, *,
      target: TextIO = sys.stdout,
      recorder_hooks: Iterable[Callable[[str], Any]] = (),
      safe_exceptions: tuple[type[BaseException], ...] = (KeyboardInterrupt, SystemExit),
      **kwargs
  ):
    # if not os.environ['TERM'].startswith('xterm'):
    #   raise TypeError('This terminal does not support XTERM ANSI escape sequences required for this application.')
    self._recorder = TermInReader(*recorder_hooks)
    self._target = target
    self._safe_exceptions = safe_exceptions
    self._config = _XtermAppConfig(**kwargs)
    self._in_app = False

  @abstractmethod
  def start(self):
    self.recorder.start()

  @property
  def in_application_context(self):
    # use this to protect subclasses' methods
    return self._in_app

  @property
  def recorder(self):
    return self._recorder

  @property
  @lru_cache
  def termsize(self):
    return shutil.get_terminal_size()

  @recorder.setter
  def recorder(self, new_recorder: TermInReader):
    if not self._recorder.normal:
      raise TypeError('unterminated recorder')
    if not isinstance(new_recorder, TermInReader):
      raise TypeError(f'recorder must be of type {TermInReader.__name__}')
    self._recorder = new_recorder

  def write(self, __s: str):
    """Simple redirected and context-protected method `write` of `target`"""
    if self.in_application_context:
      return self._target.write(__s)

  def flush(self):
    """Simple redirected and context-protected method `flush` of `target`"""
    if self.in_application_context:
      return self._target.flush()

  def __enter__(self):
    self.open()
    return self

  @final
  def open(self):
    os.system('')
    self._target.write('\x1b[?7h\x1b[?25h\x1b[?1005l\x1b[?1006l\x1b[?1015l\x1b[?1003l\x1b[?1l')
    # self.restore_defaults()
    self._target.write('\x1b[?1h')
    if self._config.alternate_buffer:
      self._target.write('\x1b[?1049h')
    if self._config.utf8_mouse:
      self._target.write('\x1b[?1005h')
    if self._config.sgr_mouse:
      self._target.write('\x1b[?1006h')
    if self._config.alternate_scroll:
      self._target.write('\x1b[?1007h')
    if self._config.urxvt_mouse:
      self._target.write('\x1b[?1015h')
    if not self._config.auto_wrap:
      self._target.write('\x1b[?7l')
    if self._config.hide_cursor:
      self._target.write('\x1b[?25l')
    if self._config.scrolling_region is not None:
      top, bottom = self._config.scrolling_region
      self._target.write(f'\x1b[{top};{bottom}r')
    if not self._config.smooth_scroll:
      self._target.write('\x1b[?4l')
    if self._config.fast_scroll:
      self._target.write('\x1b[?1014h')
    if self._config.meta_key:
      self._target.write('\x1b[?1034h')
    if self._config.alt_numlock:
      self._target.write('\x1b[?1035h')
    if self._config.mouse_events:
      self._target.write('\x1b[?1003h')
    self._in_app = True
    self._target.flush()

  def restore_defaults(self):
    # self._target.write(
    #   '\x1b[?1l\x1b[;r\x1b[?1014l\x1b[?1034l\x1b[?1035l'
    #   '\x1b[?1005l\x1b[?1006l\x1b[?1015l\x1b[?25h\x1b[?1007l'
    #   '\x1b[?1003l\x1b[?4l\x1b[?7h'
    # )
    self._target.write('\x1b[?7h\x1b[?25h\x1b[?1005l\x1b[?1006l\x1b[?1015l\x1b[?1003l\x1b[?1l')
    # self._target.write('')
    # if self.utf8_mouse:
    #   self._target.write('\x1b[?1005l')
    # if self.sgr_mouse:
    #   self._target.write('\x1b[?1006l')
    if self._config.alternate_scroll:
      self._target.write('\x1b[?1007l')
    # if self.urxvt_mouse:
    #   self._target.write('\x1b[?1015l')
    if self._config.scrolling_region is not None:
      self._target.write(f'\x1b[;r')
    if not self._config.smooth_scroll:
      self._target.write('\x1b[?4h')
    if self._config.fast_scroll:
      self._target.write('\x1b[?1014l')
    if self._config.meta_key:
      self._target.write('\x1b[?1034l')
    if self._config.alt_numlock:
      self._target.write('\x1b[?1035l')
    if self._config.alternate_buffer:
      self._target.write('\x1b[?1049l')
    # if self.mouse_events:
    #   self._target.write('\x1b[?1003l')

  def __exit__(self, __exc_type: Type[BaseException] | None, __exc_value: BaseException | None,
               __traceback: TracebackType | None) -> bool | None:
    self.close()
    if __exc_type is None or issubclass(__exc_type, self._safe_exceptions):
      return True

  @final
  def close(self):
    self.recorder.end()
    self._in_app = False
    self.restore_defaults()
    subprocess.run('stty sane', shell=True, stderr=subprocess.DEVNULL)


def contextprotected(method: _FuncT) -> _FuncT:
  @wraps(method)
  def _wrapper(self, *args, **kwargs):
    if isinstance(self, XTermApplication) and self.in_application_context:
      return method(self, *args, **kwargs)  # type: ignore
    return None

  return _wrapper  # type: ignore


@final
class XTermApplicationEmpty(XTermApplication):
  @contextprotected
  def start(self):
    super(XTermApplicationEmpty, self).start()


# turn into class
class TermInReader:
  __instances: WeakSet[TermInReader] = WeakSet()
  __func: Callable[[str], Any]
  hooks: tuple[Callable[[str], Any], ...]
  bindings: dict[str, list[Callable[[], Any] | partial[Any]]]
  _which: int = 0

  def __init__(self, *hooks: Callable[[str], Any]) -> None:
    self.__instances.add(self)
    self.hooks = hooks
    self.__func = hooks[0] if hooks else lambda _: None
    self.normal = True
    self._old_settings = None
    self.bindings = {}

  def input(self, __prompt: str, max_chars: int | None = None):
    if max_chars is None or self.normal:
      subprocess.run('stty sane', stderr=subprocess.DEVNULL, shell=True)
      return input(__prompt)
    else:
      self.end()
      sys.stdout.write(__prompt)
      sys.stdout.flush()
      return sys.stdin.read(max_chars)

  def bind(self, code: Ctrl | str, func: Callable[[], Any] | partial):
    if isinstance(code, Ctrl):
      for _code in code.codes:
        self.bind(_code, func)
    else:
      self.bindings.setdefault(code, []).append(func)

  def switch_hook(self, advance: int = 1):
    self._which += advance
    self._which %= len(self.hooks)
    self.__func = self.hooks[self._which]

  def new_settings(self):
    if S_ISFIFO(os.fstat(0).st_mode):
      raise TypeError('Cannot read keyboard input from stdin when piped')
    if self.normal:
      try:
        import tty, termios
        if sys.stdin.closed:
          raise TypeError('stdin is closed')
        tty.setraw(sys.stdin.fileno())
        if not self._old_settings:
          self._old_settings = termios.tcgetattr(sys.stdin)
        new_settings = termios.tcgetattr(sys.stdin)
        new_settings[3] = new_settings[3] & ~(termios.ECHO | termios.ICANON)  # lflags
        new_settings[6][termios.VMIN] = 0  # cc
        new_settings[6][termios.VTIME] = 0  # cc
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)
      except ImportError:
        pass
      finally:
        self.normal = False

  def end(self):
    if not self.normal:
      try:
        import termios
        if not sys.stdin.closed:
          termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_settings)
      except ImportError:
        pass
      finally:
        if not sys.stdin.closed:
          sys.stdin.flush()
        self.normal = True

  def start(self, timeout: float | None = None) -> None:
    if any(not instance.normal for instance in self.__instances if instance is not self):
      raise TypeError('conflicting terminal recorders')
    self.new_settings()
    try:
      self.record(timeout)
    except (KeyboardInterrupt, SystemExit):
      pass
    finally:
      self.end()

  def record(self, timeout: float | None = None):
    self.normal = False
    try:
      ready, _, _ = select.select([sys.stdin], [], [], timeout)
      while ready and not self.normal:
        # key = sys.stdin.read()
        b = sys.stdin.buffer.read()
        try:
          key = b.decode('utf-8')
        except UnicodeDecodeError:
          key = b.decode('iso-8859-1')
        if len(key):
          self._handle(key)
    except OSError:
      import msvcrt
      start = time.perf_counter()
      key = ''
      while not self.normal:
        try:
          if msvcrt.kbhit():
            key = msvcrt.getwch()
            # key = sys.stdin.read()
            # print(repr(key))
            self._handle(key if key not in ('\xe0', '\x00') else (key + msvcrt.getwch()))
          if len(key) == 0 and timeout is not None and time.perf_counter() - start > timeout:
            return
          time.sleep(0)
        except KeyboardInterrupt:
          self._handle('\x03')

  def _handle(self, key: str) -> None:
    for f in self.bindings.get(key, []):
      f()
    if key == '\x04':
      # rescue key
      self.end()
      sys.exit(1)
    self.__func(key)
    # return _wrapper

  def __hash__(self) -> int:
    return id(self)


@functools.lru_cache
def _unicode_len(string: str) -> int:
  return sum({'F': 2, 'W': 2}.get(unicodedata.east_asian_width(char), 1) for char in string)


class LineBuffer:
  _local_history: list[str]
  _line: str
  _pos: int
  _history_pos: int
  _prompt: str
  __send_with_enter: bool
  __cursor_movement: bool
  __use_history: bool
  __tabsize: int

  def __init__(self,
               *,
               send_with_enter: bool = True,
               cursor_movement: bool = True,
               use_history: bool = True,
               tabsize: int = 4) -> None:
    self.reset()
    self._local_history = []
    self.__send_with_enter = send_with_enter
    self.__cursor_movement = cursor_movement
    self.__use_history = use_history
    self.__tabsize = tabsize

  def reset(self) -> None:
    self._line = ''
    self._pos = 0  # absolute position
    self._history_pos = 0
    self._prompt = ''

  @property
  def pos(self):
    return self._pos + 1

  @property
  def prompt(self):
    return self._prompt

  @prompt.setter
  def prompt(self, _prompt: str):
    # self._recalculate(self._prompt, _prompt)
    offset = self._pos - len(self._prompt)
    self._pos = len(_prompt) + offset
    self._prompt = _prompt

  # @placeholder.setter
  def set_placeholder(self, placeholder: str):
    if not self._line:
      self._line = placeholder
      self._pos = len(self._prompt + placeholder)

  @property
  def line(self):
    return self._line

  def cursor_left(self, n: int = 1):
    offset = self._pos - len(self._prompt)
    # if valid := (self._pos > len(self._prompt)):
    if valid := (offset > 0):
      self._pos -= min(n, offset)
    return valid

  def cursor_right(self, n: int = 1):
    offset = len(self._prompt + self._line) - self._pos
    if valid := (offset > 0):
      self._pos += min(n, offset)
    return valid

  def history_up(self):
    if self._history_pos == 0 or self._history_pos < len(self._local_history) - 1:
      if self._history_pos == 0:
        self._local_history.append(self._line)
      self._history_pos += 1
      self._line = self._local_history[-self._history_pos - 1]
      self._pos = len(self._line) + len(self._prompt)

  def history_down(self):
    if self._history_pos > 0:
      self._history_pos -= 1
      self._line = self._local_history.pop() if self._history_pos == 0 else self._local_history[-self._history_pos - 1]
      self._pos = len(self._line) + len(self._prompt)

  def enter_send(self):
    if not self._local_history or self._line != self._local_history[-1]:
      if self._history_pos != 0:
        self._local_history.pop()
      self._local_history.append(self._line)
    result = self._line
    self._line = ''
    self._pos = len(self._prompt)
    return result

  def insert(self, char: str):
    if char != Ctrl.ENTER and char.isspace() or len(char) == 1 and ord(char) not in range(0x00, 0x20):
      self._line = f'{self._line[:self._pos]}{char}{self._line[self._pos:]}'
      self._pos += 1

  def key(self, char: str) -> str | None:
    # if char == '\b' and self._pos < len(self._line) or char in ('\x7f', '\x08') and self._left():
    if char in (Ctrl.DEL, Ctrl.BACKSPACE):
      if char == Ctrl.DEL and self._pos < len(self._prompt + self._line) or char == Ctrl.BACKSPACE and self.cursor_left():
        true_pos = self._pos - len(self._prompt)
        self._line = self._line[:true_pos] + self._line[true_pos + 1:]
    elif char == Ctrl.TAB:
      self.insert('\t'.expandtabs(self.__tabsize))
    else:
      self.insert(char)
      if self.__cursor_movement:
        if char == Ctrl.R_ARROW:
          self.cursor_right()
        elif char == Ctrl.L_ARROW:
          self.cursor_left()
        elif char == Ctrl.HOME:
          self.cursor_left(len(self._line))
        elif char == Ctrl.END:
          self.cursor_right(len(self._line))
        elif char in (Ctrl.CTRL_LARROW, Ctrl.OPT_LARROW):
          true_pos = self._pos - len(self._prompt)
          substr = self._line[0:true_pos]
          offset = true_pos - m.end() if (m := re.search(r'.*(?<!\s)(?=\s+\S+)', substr)) else len(self._line)
          self.cursor_left(offset)
        elif char in (Ctrl.CTRL_RARROW, Ctrl.OPT_RARROW):
          true_pos = self._pos - len(self._prompt)
          offset = m.end() + 1 if (m := re.search(r'\s+(?=\S)', self._line[true_pos + 1:])) else len(self._line)
          self.cursor_right(offset)
      if self.__use_history:
        if char == Ctrl.U_ARROW:
          self.history_up()
        elif char == Ctrl.D_ARROW:
          self.history_down()
      if self.__send_with_enter:
        if char == Ctrl.ENTER:
          return self.enter_send()

  def with_csi(self) -> str:
    # return f'\x1b[2K\x1b[0G{self._prompt}{self._line}\x1b[{self._pos + 1}G'
    return f'\x1b[2K\x1b[0G{self._prompt}{self._line}\x1b[{_unicode_len(self._line[:self._pos]) + 1}G'


def instant_input(__prompt: str = '', max_char: int | None = None) -> str:
  """If `max_char` is given, tweaks ``stdin`` such that only `max_char` characters are read before it terminates.
  Otherwise, it is equivalent to ``input(__prompt)``."""
  if max_char and not S_ISFIFO(os.fstat(0).st_mode):
    try:
      import termios
      old = termios.tcgetattr(sys.stdin.fileno())
      new = termios.tcgetattr(sys.stdin.fileno())
      new[3] = new[3] & ~termios.ICANON
      # new[6][termios.VMIN] = 0
      new[6][termios.VTIME] = 0
      termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, new)
      sys.stdout.write(__prompt)
      sys.stdout.flush()
      answer = sys.stdin.read(max_char)
      sys.stdout.write('\n')
      termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)
      # subprocess.run('stty sane', shell=True, stderr=subprocess.DEVNULL)
      os.system('stty sane')
      return '' if answer in '\r\n' else answer
    except (OSError, ImportError):
      import msvcrt

      def _read():
        char = msvcrt.getwch()
        if char == '\x03':
          sys.stdout.write('^C')
          raise KeyboardInterrupt
        sys.stdout.write(char)
        return char

      sys.stdout.write(__prompt)
      sys.stdout.flush()
      answer = ''.join(_read() for _ in range(max_char))
      sys.stdout.write('\n')
      return '' if answer in '\r\n' else answer
  else:
    return input(__prompt)
