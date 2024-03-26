from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from typing import Callable, Any, Literal, Iterable, Generic, TypeVar

from term_app_pack.utils import Ctrl, SequencePointer, trim
from term_app_pack.termutils import XTermApplication, LineBuffer, contextprotected

_T = TypeVar('_T')

RE_ANSI: re.Pattern[str] = re.compile(r'\x1B[@-Z\\-_]|[\x80-\x9A\x9C-\x9F]|(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~]')


class BaseMenu(XTermApplication):
  menus: list[_Menu]

  def __init__(self, *initial_menus: _Menu[_T]):
    self.menus = list(initial_menus)
    XTermApplication.__init__(self, hide_cursor=True, recorder_hooks=(self.simple_nav,))
    self.recorder.bind(Ctrl.CTRL_X, self.exit)
    self.recorder.bind(Ctrl.CTRL_C, self.exit)

  def exit(self):
    self.cleanup()
    self.close()

  def simple_nav(self, key: str):
    menu = self.menus[-1]
    if key == Ctrl.ESC and len(self.menus) > 1:
      self.display(use_previous=True)
    elif key == Ctrl.ENTER:
      item = menu.items[menu.items.pointer][1]
      if menu.selector:
        menu.selector(item)
      elif callable(item):
        item()
      else:
        raise TypeError('internal error: no selector and item not callable')
    else:
      vertical, horizontal = menu.mode == 'vertical', menu.mode == 'horizontal'
      if vertical and key == Ctrl.D_ARROW or horizontal and key == Ctrl.R_ARROW:
        menu.items.next()
      elif vertical and key == Ctrl.U_ARROW or horizontal and key == Ctrl.L_ARROW:
        menu.items.previous()
      self.display()

  @contextprotected
  def display(self, use_previous: bool = False, cleanup: bool = True):
    if cleanup:
      self.cleanup()
    if use_previous:
      self.menus.pop()
    menu = self.menus[-1]
    if menu.mode == 'horizontal':
      _len = self.termsize.columns
      item_len = _len // len(menu.items)
      items = (f'{trim(item[0], item_len):<{item_len}}' for item in menu.items)
      items = (f'\x1b[7m{item}\x1b[0m' if i == menu.items.pointer else item for i, item in enumerate(items))
      self.write(''.join(items))
    elif menu.mode == 'vertical':
      _len = min(max(map(len, menu.items)), self.termsize.columns)
      items = (f'{trim(item[0], _len):<{_len}}' for item in menu.items)
      items = (f'\x1b[7m{item}\x1b[0m' if i == menu.items.pointer else item for i, item in enumerate(items))
      self.write('\x1b[E'.join(items))
    self.write('\r\n')

  @contextprotected
  def cleanup(self):
    self.write('\x1b[0J')
    menu = self.menus[-1]
    if menu.mode == 'vertical':
      self.write('\x1b[F\x1b[2K' * len(menu.items))
    else:
      self.write('\x1b[F\x1b[2K')

  def add_menu(self, menu: _Menu[_T], default_pos: int = 0):
    self._add_menu(menu, default_pos)

  def add_new_menu(self, items: SequencePointer[tuple[str, _T]],
                   selector: Callable[[_T], Any] | None = None,
                   mode: Literal['vertical', 'horizontal'] = 'horizontal',
                   default_pos: int = 0):
    self._add_menu(self._Menu(items, selector, mode), default_pos)

  def _add_menu(self, menu: _Menu[_T], default_pos: int = 0):
    if self.in_application_context:
      self.cleanup()
    menu.items.pointer = default_pos
    self.menus.append(menu)
    if self.in_application_context:
      self.display(cleanup=False)

  def start(self):
    self.display(cleanup=False)
    super(BaseMenu, self).start()

  @dataclass
  class _Menu(Generic[_T]):
    items: SequencePointer[tuple[str, _T]]
    selector: Callable[[_T], Any] | None = None
    mode: Literal['vertical', 'horizontal'] = 'horizontal'


class FuzzyFinder(XTermApplication):
  """Emulates fzf (fuzzy finder)"""
  _start_index: int
  _maxlines: int
  objects: list[str]
  _value: str | None
  _sublist: SequencePointer[str]
  _current_query: str
  _line_buffer: LineBuffer
  _receiver: Callable[[str], Any] | None

  def __init__(self, objects: Iterable[str], receiver: Callable[[str], Any] | None = None):
    XTermApplication.__init__(
      self,
      alternate_buffer=True,
      alternate_scroll=True,
      auto_wrap=False,
      mouse_events=True,
      recorder_hooks=(self.handle_key,)
    )
    self.objects = list(objects)
    self.recorder.bind(Ctrl.CTRL_C, self.exit)
    self.recorder.bind(Ctrl.CTRL_D, self.exit)
    self.recorder.bind(Ctrl.D_ARROW, self.next_item)
    self.recorder.bind(Ctrl.U_ARROW, self.previous_item)
    self.recorder.bind(Ctrl.PG_UP, functools.partial(self.previous_item, len(self.objects)))
    self.recorder.bind(Ctrl.PG_DOWN, functools.partial(self.next_item, len(self.objects)))
    self.recorder.bind(Ctrl.ENTER, self.send)
    self._receiver = receiver
    self._sublist = SequencePointer(self.objects, False)
    self._value = None
    self._start_index = 0
    self._maxlines = self.termsize.lines - 2
    self._line_buffer = LineBuffer(send_with_enter=False, use_history=False)
    self._current_query = ''

  def exit(self):
    self._value = None
    self.close()

  @property
  def value(self):
    return self._value

  @contextprotected
  def start(self):
    self.footer()
    self.writelines()
    self.highlight(self._sublist.pointer)
    self.search_bar()
    self.flush()
    super(FuzzyFinder, self).start()

  def handle_key(self, key: str):
    self.previous_item(up := key.count('\x1b[M`'))
    self.next_item(down := key.count('\x1b[Ma'))
    if up == down == 0:
      self._line_buffer.key(key)
    self.search_bar()

  @contextprotected
  def clear(self):
    self.write('\x1b[0;0H\x1b[2K' + '\x1b[E\x1b[2K' * (self._maxlines - 1))

  @contextprotected
  def writelines(self):
    self.footer()
    if not len(self._sublist):
      self.clear()
      self.write('\x1b[0;0H\x1b[7m(EMPTY)\x1b[0m')
    else:
      self.write('\x1b[0;0H\x1b[2K')
      # sys.stdout.write('\x1b[E\x1b[2K'.join(self._sublist[self._start_index:self._start_index + self._maxlines]))
      self.write(
        '\x1b[E\x1b[2K'.join(
          self._format_normal_line(line, self.termsize.columns)
          for line in self._sublist[self._start_index:self._start_index + self._maxlines]
        )
      )
      self.flush()

  @contextprotected
  def footer(self):
    self.write(f'\x1b[{self.termsize.lines - 1};0H')
    total = len(self._sublist)
    display_count = min(self._maxlines, total)
    start = self._start_index
    self.write(
      '{count:\u2500<{length}}'.format(
        count=f'{self._sublist.pointer + 1}/{start + 1 if total else 0}-{start + display_count}/{total} ',
        length=self.termsize.columns
      )
    )

  @contextprotected
  def search_bar(self):
    if (query := self._line_buffer.line) != self._current_query:
      self._current_query = query
      if query == '':
        self._sublist = SequencePointer(self.objects, False)
        self._start_index = 0
        self.writelines()
        self.highlight(0)
      else:
        self._sublist = SequencePointer(
          sorted(
            (obj for obj in self.objects if self._matches_query(query, obj)),
            key=lambda obj: self._matches_query(query, obj)[1],
            reverse=True
          ), False
        )
        self._start_index = 0
        self.clear()
        self.writelines()
        self.highlight(0)
    self.write(f'\x1b[{self.termsize.lines};0H\x1b[2K')
    self.write(self._line_buffer.with_csi())
    self.flush()

  @contextprotected
  def highlight(self, index: int, unhighlight: bool = False):
    # assumes index in range
    if index < len(self._sublist):
      row = 1 + index - self._start_index
      self.write(f'\x1b7\x1b[{row};0H')
      if unhighlight:
        self.write(f'\x1b[0K{self._format_normal_line(self._sublist[index], self.termsize.columns)}')
      else:
        self.write(self.rjust_line(
          f'\x1b[48;5;22m \x1b[2;39m\u2590\x1b[22m \x1b[31;1m>\x1b[39;22m {self._format_item(self._sublist[index])}'
        ))
        self.write('\x1b[0m')
        # f'{self._format_item(self._sublist[index]):<{self.termsize.columns}}\x1b[0m')
      self.write('\x1b8')

  def rjust_line(self, item: str) -> str:
    # print(item, len(re.sub(RE_ANSI, '', item)))
    width = self.termsize.columns - len(re.sub(RE_ANSI, '', item))
    return item + ' ' * width

  def next_item(self, n: int = 1):
    if len(self._sublist):
      self.highlight(self._sublist.pointer, unhighlight=True)
      self._sublist.next(n)
      if (pointer := self._sublist.pointer) >= self._start_index + self._maxlines:
        self.scroll_down(pointer - self._start_index - self._maxlines + 1)
      self.highlight(pointer)
      self.footer()
      self.flush()

  def previous_item(self, n: int = 1):
    if len(self._sublist):
      self.highlight(self._sublist.pointer, unhighlight=True)
      self._sublist.previous(n)
      if (pointer := self._sublist.pointer) < self._start_index:
        self.scroll_to_view()
      self.highlight(pointer)
      self.footer()
      self.flush()

  def scroll_to_view(self):
    if (offset := self._sublist.pointer - self._start_index) not in range(0, self._maxlines):
      (self.scroll_up if offset < 0 else self.scroll_down)(abs(offset))

  def scroll_up(self, n: int = 1):
    if self._start_index > 0:
      self._start_index -= min(n, self._start_index)
      self.writelines()

  def scroll_down(self, n: int = 1):
    if self._start_index + self._maxlines < (listsize := len(self._sublist)):
      self._start_index += min(n, listsize - self._start_index - self._maxlines)
      self.writelines()

  @functools.lru_cache
  def _matches_query(self, query: str, item: str):
    i_item = item.casefold()
    score = 0
    indices: list[int] = []
    last_index = -1
    for char in query:
      if (i := i_item.find(char.casefold(), last_index + 1)) == -1:
        return
      indices.append(i)
      _score = (i - last_index - 1) * 0.05
      score += 0.5 + _score if item[i] != char else 1 + _score
      last_index = i
    if indices:
      return indices, score / (last_index + 1)

  def _format_normal_line(self, item: str, length: int) -> str:
    return f' \x1b[2;39m\u2590\x1b[0m   {self._format_item(trim(item, length - 5))}'

  def _format_item(self, item: str):
    if (query := self._current_query) and (match := self._matches_query(query, item)):
      for i in reversed(match[0]):
        item = f'{item[:i]}\x1b[1;36m{item[i]}\x1b[22;39m{item[i + 1:]}'
    return item

  def send(self):
    if len(self._sublist):
      self.recorder.end()
      self._value = self._sublist[self._sublist.pointer]
      if self._receiver:
        self._receiver(self._sublist[self._sublist.pointer])
