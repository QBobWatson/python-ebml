"""
Container classes.
"""

from bisect import bisect_left, bisect_right
from operator import itemgetter
from collections.abc import Sequence, MutableSequence, MutableMapping

class SortedList(Sequence):
    """Sequence sorted by a key function.

    SortedList() is much easier to work with than using bisect() directly.
    It supports key functions like those use in sorted(), min(), and max().
    The result of the key function call is saved so that keys can be searched
    efficiently.

    Instead of returning an insertion-point which can be hard to interpret, the
    five find-methods return a specific item in the sequence. They can scan for
    exact matches, the last item less-than-or-equal to a key, or the first item
    greater-than-or-equal to a key.

    Once found, an item's ordinal position can be located with the index()
    method.  New items can be added with the insert() and insert_right()
    methods.  Old items can be deleted with the remove() method.

    The usual sequence methods are provided to support indexing, slicing,
    length lookup, clearing, copying, forward and reverse iteration, contains
    checking, item counts, item removal, and a nice looking repr.

    Finding and indexing are O(log n) operations while iteration and insertion
    are O(n).  The initial sort is O(n log n).

    The key function is stored in the 'key' attibute for easy introspection or
    so that you can assign a new key function (triggering an automatic re-sort).

    In short, the class was designed to handle all of the common use cases for
    bisect but with a simpler API and support for key functions.

    Attributes:
        key: the key function used for sorting

    Usage:
    >>> from pprint import pprint
    >>> from operator import itemgetter

    >>> s = SortedList(key=itemgetter(2))
    >>> for record in [
    ...         ('roger', 'young', 30),
    ...         ('angela', 'jones', 28),
    ...         ('bill', 'smith', 22),
    ...         ('david', 'thomas', 32)]:
    ...     s.insert(record)

    >>> pprint(list(s))         # show records sorted by age
    [('bill', 'smith', 22),
     ('angela', 'jones', 28),
     ('roger', 'young', 30),
     ('david', 'thomas', 32)]

    >>> s.find_le(29)           # find oldest person aged 29 or younger
    ('angela', 'jones', 28)
    >>> s.find_lt(28)           # find oldest person under 28
    ('bill', 'smith', 22)
    >>> s.find_gt(28)           # find youngest person over 28
    ('roger', 'young', 30)

    >>> r = s.find_ge(32)       # find youngest person aged 32 or older
    >>> s.index(r)              # get the index of their record
    3
    >>> s[3]                    # fetch the record at that index
    ('david', 'thomas', 32)

    >>> s.key = itemgetter(0)   # now sort by first name
    >>> pprint(list(s))
    [('angela', 'jones', 28),
     ('bill', 'smith', 22),
     ('david', 'thomas', 32),
     ('roger', 'young', 30)]

    From http://code.activestate.com/recipes/577197-sortedcollection/
    """

    def __init__(self, iterable=(), key=None):
        """Creates a new SortedList object.

        Creates a SortedList object from an iterable.  The iterable is sorted
        using the key function, if given.  The default key function is the
        identity function, i.e. an object is its own key.

        Args:
            iterable: Add the values of this iterable to the SortedList.
            key: A key function like those used in sorted(), min(), etc.
        Returns:
            A new SortedList object.
        """
        self._given_key = None
        self._keys = None
        self._items = None
        self._key = None
        self._sortedlist_init(iterable, key)

    def _sortedlist_init(self, iterable=(), key=None):
        """Actually initialize the object.

        This is here in case a subclass redefines the __init__() signature.
        """
        self._given_key = key
        key = (lambda x: x) if key is None else key
        decorated = sorted(((key(item), item) for item in iterable),
                           key=itemgetter(0))
        self._keys = [k for k, item in decorated]
        self._items = [item for k, item in decorated]
        self._key = key

    @property
    def key(self):
        """Returns the current key function"""
        return self._key
    @key.setter
    def key(self, key):
        """Update self.key, triggering a resort."""
        if key is not self._key:
            self._sortedlist_init(self._items, key)
    @key.deleter
    def key(self):
        """Reset to the default key function, triggering a resort."""
        self.key = None

    def re_sort(self):
        """Update keys and re-sort the list."""
        self._sortedlist_init(self._items, self.key)

    def clear(self):
        """Delete all contained objects."""
        self._sortedlist_init([], self._key)

    def copy(self):
        """Performs a shallow copy of this object."""
        return self.__class__(self, self._key)

    def __eq__(self, other):
        #pylint: disable=protected-access
        return self._items == other._items

    def __ne__(self, other):
        #pylint: disable=protected-access
        return self._items != other._items

    def __len__(self):
        return len(self._items)

    def __getitem__(self, i):
        return self._items[i]

    def __delitem__(self, i):
        del self._keys[i]
        del self._items[i]

    def __iter__(self):
        return iter(self._items)

    def __reversed__(self):
        return reversed(self._items)

    def __repr__(self):
        return '{}({!r}, key={})' \
            .format(self.__class__.__name__, self._items,
                    getattr(self._given_key, '__name__', repr(self._given_key)))

    def __reduce__(self):
        return self.__class__, (self._items, self._given_key)

    def __contains__(self, item):
        k = self._key(item)
        i = bisect_left(self._keys, k)
        j = bisect_right(self._keys, k)
        return item in self._items[i:j]

    def index(self, item):
        """Find the position of an item.  Raise ValueError if not found."""
        k = self._key(item)
        i = bisect_left(self._keys, k)
        j = bisect_right(self._keys, k)
        return self._items.index(item, i, j)

    def count(self, item):
        """Return number of occurrences of item"""
        k = self._key(item)
        i = bisect_left(self._keys, k)
        j = bisect_right(self._keys, k)
        return self._items[i:j].count(item)

    def insert(self, item):
        """Insert a new item.  If equal keys are found, add to the left"""
        k = self._key(item)
        i = bisect_left(self._keys, k)
        self._keys.insert(i, k)
        self._items.insert(i, item)

    def insert_right(self, item):
        """Insert a new item.  If equal keys are found, add to the right"""
        k = self._key(item)
        i = bisect_right(self._keys, k)
        self._keys.insert(i, k)
        self._items.insert(i, item)

    def remove(self, item):
        """Remove first occurence of item.  Raise ValueError if not found"""
        i = self.index(item)
        del self._keys[i]
        del self._items[i]

    def find(self, k):
        """Return first item with a key == k.  Raise ValueError if not found."""
        i = bisect_left(self._keys, k)
        if i != len(self) and self._keys[i] == k:
            return self._items[i]
        raise ValueError('No item found with key equal to: {!r}'.format(k))

    def index_le(self, k):
        """Return the index of the last item with key <= k"""
        i = bisect_right(self._keys, k)
        if i:
            return i-1
        raise ValueError('No item found with key at or below: {!r}'.format(k))

    def find_le(self, k):
        """Return last item with a key <= k.  Raise ValueError if not found."""
        return self._items[self.index_le(k)]

    def index_lt(self, k):
        """Return index of the last item with key < k"""
        i = bisect_left(self._keys, k)
        if i:
            return i-1
        raise ValueError('No item found with key below: {!r}'.format(k))

    def find_lt(self, k):
        """Return last item with a key < k.  Raise ValueError if not found."""
        return self._items[self.index_lt(k)]

    def index_ge(self, k):
        """Return index of the first item with key >= k"""
        i = bisect_left(self._keys, k)
        if i != len(self):
            return i
        raise ValueError('No item found with key at or above: {!r}'.format(k))

    def find_ge(self, k):
        """Return first item with a key >= k.  Raise ValueError if not found"""
        return self._items[self.index_ge(k)]

    def index_gt(self, k):
        """Return the index of the first item with key > k"""
        i = bisect_right(self._keys, k)
        if i != len(self):
            return i
        raise ValueError('No item found with key above: {!r}'.format(k))

    def find_gt(self, k):
        """Return first item with a key > k.  Raise ValueError if not found"""
        return self._items[self.index_gt(k)]


class ProtectedDict(MutableMapping):
    """A dict-like class supporting custom a set item method.

    Inheriting this class should behave exactly like inheriting dict, except all
    item mutator access (not including deleting items) is guaranteed to go
    through the __setitem__() method.

    Attributes:
        _dict: the underlying dictionary
    """

    def __init__(self, **kwargs):
        self._dict = {}
        for key, val in kwargs.items():
            self[key] = val

    # Override this
    def __setitem__(self, key, val):
        self._dict[key] = val

    # Pure virtual
    def __getitem__(self, item):
        return self._dict[item]
    def __len__(self):
        return len(self._dict)
    def __iter__(self):
        return iter(self._dict)
    def __delitem__(self, item):
        del self._dict[item]

    # Reimplemented
    def __contains__(self, item):
        return self._dict.__contains__(item)
    def __eq__(self, other):
        return self._dict.__eq__(other)
    def __ne__(self, other):
        return self._dict.__ne__(other)
    def keys(self):
        return self._dict.keys()
    def items(self):
        return self._dict.items()
    def values(self):
        return self._dict.values()
    def get(self, key, default=None):
        return self._dict.get(key, default)
    def clear(self):
        self._dict.clear()
    def setdefault(self, key, default=None):
        self._dict.setdefault(key, default)

    # New
    def __repr__(self):
        return "{}({!r})".format(self.__class__.__name__, self._dict)
    def __str__(self):
        return repr(self)


class ProtectedList(MutableSequence):
    """A list-like class supporting a custom set item method.

    Inheriting this class should behave like inheriting list, except all item
    mutator access (not including reordering or deleting items) is guaranteed to
    go through the __setitem__() or insert() methods.

    Attributes:
        _list: the underlying list
    """

    def __init__(self, iterable=None):
        self._list = []
        if iterable:
            for thing in iterable:
                self.append(thing)

    # Override these
    def __setitem__(self, i, val):
        # Default behavior
        self._list[i] = val
    def insert(self, i, item):
        "Insert item before index i"
        # Default behavior
        self._list.insert(i, item)

    # Pure virtual
    def __getitem__(self, item):
        return self._list[item]
    def __len__(self):
        return len(self._list)
    def __delitem__(self, i):
        del self._list[i]

    # Reimplemented
    def __contains__(self, item):
        return item in self._list
    def __iter__(self):
        return iter(self._list)
    def __reversed__(self):
        return reversed(self._list)
    def index(self, value):
        return self._list.index(value)
    def count(self, value):
        return self._list.count(value)
    def reverse(self):
        self._list.reverse()
    def pop(self, index=-1):
        return self._list.pop(index)
    def remove(self, value):
        self._list.remove(value)

    # New
    def __repr__(self):
        return "{}({!r})".format(self.__class__.__name__, self._list)
    def __str__(self):
        return repr(self)


__all__ = ['SortedList', 'ProtectedDict', 'ProtectedList']

