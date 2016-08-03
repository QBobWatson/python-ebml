"""
The Parsed property.
"""

__all__ = ['Parsed', 'create_atomic']

class Parsed:
    """Property that gets and sets its value from child elements."""
    #pylint: disable=too-few-public-methods
    #pylint: disable=too-many-instance-attributes

    unset = object() # For distinguishing unset from None

    def __init__(self, name_or_id, getter, setter=None, creator=None,
                 deleter=None, default=unset, skip=unset):
        """Make a new Parsed property.

        Args:
         + name_or_id: The name or EBML ID of the child element in which to find
           the property value.
         + getter: A function getter(self, child) that takes a child and returns
           its value.  If a string, return the child's attribute of that name.
           If the empty string '', return the child itself.
         + setter: A function setter(self, child, val) that sets the value of
           child to val.  If a string, set the child's attribute of that name.
           If None, or if no such child exists and self.creator is None, raise
           AttributeError when trying to set the attribute.
         + creator: A function creator(self, ebml_id, val) that takes a value
           and returns a new child element containing val.  The new child is
           then appended to the owner object.  The ebml_id argument is set to
           self.ebml_id.
         + deleter: A function deleter(self, ebml_id) that deletes the child
           Element from self.  If set to None, deleting the property deletes all
           children with a given ebml_id.  If set to False, disable deleting.
         + default: The value of the property if the child element is not found.
           If unset, use the default value of the Tag for this property.  Does
           not work if the Tag's default value is a sibling Tag.  As a last
           resort, use None.  If this is callable, run default(self) to get the
           default.  This works with attrgetter().
         + skip: If set, if getter returns a value equal to skip, ignore that
           child.  Used to skip children whose value is unset and continue
           searching for a child whose value is set.
        """
        #pylint: disable=too-many-arguments
        self._name_or_id = name_or_id
        self.tag = None
        self.ebml_id = None
        self.name = None
        self.getter = getter
        self.setter = setter
        self.creator = creator
        self.deleter = deleter
        self.default = default
        self.skip = skip

    def delayed_init(self):
        "Get tag information.  Needs to happen after MATROSKA_TAGS is defined."
        from .tags import MATROSKA_TAGS
        if self.tag is None:
            self.tag = MATROSKA_TAGS[self._name_or_id]
            self.ebml_id = self.tag.ebml_id
            self.name = self.tag.name

    def __get__(self, instance, owner):
        self.delayed_init()
        children = list(instance.children_with_id(self.ebml_id))
        for child in reversed(children):
            if isinstance(self.getter, str):
                if self.getter == '':
                    value = child
                else:
                    value = getattr(child, self.getter)
            else:
                value = self.getter(instance, child)
            if self.skip is not self.unset and value == self.skip:
                continue
            return value
        # Use default
        if self.default is not self.unset:
            if callable(self.default):
                return self.default(instance)
            return self.default
        # Use default default
        return getattr(self.tag, 'default', None)

    def __set__(self, instance, value):
        self.delayed_init()
        if self.setter is None:
            raise AttributeError("Tried to set read-only Parsed property")
        children = list(instance.children_with_id(self.ebml_id))
        if not children:
            if not self.creator:
                raise AttributeError("Tried to set child value, "
                                     "but no such child exists")
            child = self.creator(instance, self.ebml_id, value)
            instance.add_child(child)
            return
        child = children[-1]
        if isinstance(self.setter, str):
            setattr(child, self.setter, value)
        else:
            self.setter(instance, child, value)

    def __delete__(self, instance):
        self.delayed_init()
        if callable(self.deleter):
            self.deleter(instance, self.ebml_id)
        elif self.deleter is None:
            for child in list(instance.children_with_id(self.ebml_id)):
                instance.remove_child(child)
        else:
            raise AttributeError("Tried to delete undeletable parsed property")

def create_atomic(childcls=None):
    """Return a function that creates a child using new_with_value.

    The return value is a function (closure) of the form
       creator(obj, ebml_id, val)
    that runs childcls.new_with_value(self.ebml_id, val).
    Suitable for use as a Parsed creator.

    Args:
    + childcls: The class to create.  Must have a new_with_value class method.
      If None, use the class of the tag for ebml_id.
    """
    def creator(instance, ebml_id, val):
        "Create an element using new_with_value()."
        #pylint: disable=unused-argument
        from .tags import MATROSKA_TAGS
        if childcls is None:
            cls = MATROSKA_TAGS[ebml_id].cls
        else:
            cls = childcls
        return cls.new_with_value(ebml_id, val)

    return creator
