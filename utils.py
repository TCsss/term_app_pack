from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
import functools
from typing import Generic, TypeVar
import unicodedata


def _join(ctrl0: Ctrl, *ctrls: Ctrl) -> tuple[str, ...]:
  _ctrls: tuple[str | tuple[str, ...], ...] = (ctrl0, *ctrls)  # type: ignore
  return sum(((ctrl,) if isinstance(ctrl, str) else ctrl for ctrl in _ctrls), ())


@functools.lru_cache
def trim(string: str, precision: int, rstart: int = 0) -> str:
  """Trims a `string` to a `precision` if needed,
  and replaces the string from `rstart` with '...', otherwise nothing is done."""
  if 3 <= precision <= len(string):
    return f"{string[:precision - rstart - 3]}...{string[len(string) - rstart:]}"
  return string


_T = TypeVar('_T')


class SequencePointer(list[_T], Generic[_T]):
  # _seq: list[_T]
  _pointer: int
  __cycle: bool

  def __init__(self, sequence: Iterable[_T], __cycle: bool = True):
    # self._seq = list(sequence)
    self._pointer = 0
    self.__cycle = __cycle
    super(SequencePointer, self).__init__(sequence)

  def next(self, n: int = 1) -> int:
    _next = self._pointer + n
    _len = self.__len__()
    if _next + 1 > _len:
      self._pointer = _next - _len if self.__cycle else _len - 1
    else:
      self._pointer = _next
    return self._pointer

  def previous(self, n: int = 1) -> int:
    _prev = self._pointer - n
    _len = self.__len__()
    if _prev < 0:
      self._pointer = _len + _prev if self.__cycle else 0
    else:
      self._pointer = _prev
    return self._pointer

  @property
  def at_end(self):
    return not self.__cycle and self._pointer == len(self) - 1

  @property
  def pointer(self) -> int:
    return self._pointer

  @pointer.setter
  def pointer(self, new_position: int) -> None:
    self._pointer = new_position if new_position < len(self) else len(self) - 1


class Ctrl(Enum):
  codes: frozenset[str]

  def __init__(self, *codes: str):
    self.codes = frozenset(codes)

  def __eq__(self, other):
    if isinstance(other, str):
      return other in self.codes
    return NotImplemented

  def __hash__(self) -> int:
    return hash(self.codes)

  ESC = '\x1b'
  ENTER = '\r', '\n', '\x1bOM'
  TAB = '\t', '\x1bOI'
  SPACE = ' ', '\x1bO '
  INSERT = '\x1b[2~'
  DEL = '\x2e', '\x1b[3~', '\x00S', '\xe0S'
  CTRL_DEL = '\xe0\x93', '\x00\x93'
  BACKSPACE = '\x7f', '\x08'
  CTRL_BS = '\x17'
  L_ARROW = '\x1b[D', '\xe0K', '\x1bOD', '\x00K'
  R_ARROW = '\x1b[C', '\xe0M', '\x1bOC', '\x00M'
  U_ARROW = '\x1b[A', '\xe0H', '\x1bOA', '\x00H'
  D_ARROW = '\x1b[B', '\xe0P', '\x1bOB', '\x00P'
  OPT_LARROW = '\x1bb'
  OPT_RARROW = '\x1bf'
  CTRL_LARROW = '\xe0s', '\x00s'
  CTRL_RARROW = '\xe0t', '\x00t'
  # HOME = '\x1b[E', '\xe0G'
  HOME = '\x1b[H', '\xe0G', '\x1bOH', '\x1b[1~', '\x00G'
  END = '\x1b[F', '\xe0O', '\x1bOF', '\x1b[4~', '\x00O'
  PG_UP = '\xe0I', '\x1b[5~', '\x00I'
  PG_DOWN = '\xe0Q', '\x1b[6~', '\x00Q'
  CTRL_A = '\x01'
  CTRL_B = '\x02'
  CTRL_C = '\x03'
  CTRL_D = '\x04'
  CTRL_E = '\x05'
  CTRL_F = '\x06'
  CTRL_G = '\x07'
  CTRL_H = '\x08'
  CTRL_I = '\x09'
  CTRL_J = '\x0a'
  CTRL_K = '\x0b'
  CTRL_L = '\x0c'
  CTRL_M = '\x0d'
  CTRL_N = '\x0e'
  CTRL_O = '\x0f'
  CTRL_P = '\x10'
  CTRL_Q = '\x11'
  CTRL_R = '\x12'
  CTRL_S = '\x13'
  CTRL_T = '\x14'
  CTRL_U = '\x15'
  CTRL_V = '\x16'
  CTRL_W = '\x17'
  CTRL_X = '\x18'
  CTRL_Y = '\x19'
  CTRL_Z = '\x1a'
  F1 = '\x1bOP', '\x00;'
  F2 = '\x1bOQ', '\x00<'
  F3 = '\x1bOR', '\x00='
  F4 = '\x1bOS', '\x00>'
  F5 = '\x1b[15~'
  F6 = '\x1b[17~'
  F7 = '\x1b[18~'
  F8 = '\x1b[19~'
  F9 = '\x1b[20~'
  F10 = '\x1b[21~'
  F11 = '\x1b[23~'
  F12 = '\x1b[24~'
  FUNCTION = _join(F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12)
  ARROW = _join(U_ARROW, D_ARROW, R_ARROW, L_ARROW)
  NAV = _join(ARROW, HOME, END, PG_UP, PG_DOWN)
  CTRL = _join(CTRL_A, CTRL_B, CTRL_C, CTRL_D, CTRL_E, CTRL_F, CTRL_G, CTRL_H, CTRL_I, CTRL_J, CTRL_K, CTRL_L, CTRL_M,
               CTRL_N, CTRL_O, CTRL_P, CTRL_Q, CTRL_R, CTRL_S, CTRL_T, CTRL_U, CTRL_V, CTRL_W, CTRL_X, CTRL_Y, CTRL_Z)


@functools.lru_cache
def _unicode_len(string: str) -> int:
  return sum({'F': 2, 'W': 2}.get(unicodedata.east_asian_width(char), 1) for char in string)
