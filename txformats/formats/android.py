from __future__ import absolute_import

import re

from ..handler import Handler, String, CopyMixin
from ..utils.test import test_handler
from ..utils.xml import DumbXml


class AndroidHandler(CopyMixin, Handler):
    name = "Android"

    plural_template = u'<item quantity="{rule}">{string}</item>'
    SPACE_PAT = re.compile(r'^\s*$')

    def parse(self, content):
        stringset = []
        if type(content) == str:
            content = content.decode("utf-8")  # convert to unicode

        resources_tag_position = content.index("<resources")
        self.source = content[resources_tag_position:]
        self.destination = ""
        self.ptr = 0
        self._order = 0

        resources_tag = DumbXml(self.source)
        last_comment = None
        for tag, offset in resources_tag.find(("string", "string-array",
                                               "plurals", DumbXml.COMMENT)):
            if tag.name == DumbXml.COMMENT:
                last_comment = tag.inner
                self.copy_until(offset + len(tag.content))
            elif tag.name == "string":
                string = self._handle_string_tag(tag, offset, last_comment)
                last_comment = None
                if string is not None:
                    stringset.append(string)
            elif tag.name == "string-array":
                for string in self._handle_string_array_tag(tag, offset,
                                                            last_comment):
                    if string is not None:
                        stringset.append(string)
            elif tag.name == "plurals":
                string = self._handle_plurals_tag(tag, offset, last_comment)
                if string is not None:
                    stringset.append(string)

        self.copy_until(len(self.source))

        template = content[:resources_tag_position] + self.destination

        del self.source
        del self.destination
        del self.ptr

        return template, stringset

    def _handle_string_tag(self, tag, offset, comment):
        string = None
        if tag.inner.strip() != "":
            string = String(tag.attrs['name'], tag.inner, order=self._order,
                            developer_comment=comment)
            self._order += 1

        # ... <string name="foo">Hello ....
        #                        ^
        self.copy_until(offset + tag.inner_offset)

        # ... ing name="foo">Hello world</stri...
        #                               ^
        if string is not None:
            self.add(string.template_replacement)
            self.skip(len(tag.inner))
        else:
            self.copy_until(offset + tag.inner_offset + len(tag.inner))

        # ...ello World</string>
        #                       ^
        self.copy_until(offset + len(tag.content))

        return string

    def _handle_string_array_tag(self, string_array_tag, string_array_offset,
                                 comment):
        # ...ing-array>   <item>H...
        #              ^
        self.copy_until(string_array_offset + string_array_tag.inner_offset)

        for index, (item_tag, item_offset) in enumerate(
                string_array_tag.find('item')):
            string = None
            if item_tag.inner.strip() != "":
                string = String(
                    "{}[{}]".format(string_array_tag.attrs['name'], index),
                    item_tag.inner,
                    order=self._order,
                    developer_comment=comment
                )
                self._order += 1
                yield string

            # ... <item>Hello...
            #           ^
            self.copy_until(string_array_offset + item_offset +
                            item_tag.inner_offset)

            # ...ello world</item>...
            #              ^
            if string is not None:
                self.add(string.template_replacement)
                self.skip(len(item_tag.inner))
            else:
                self.copy_until(string_array_offset + item_offset +
                                len(item_tag.inner))

            # orld</item>   <it...
            #            ^
            self.copy_until(string_array_offset + item_offset +
                            len(item_tag.content))

        # </item>  </string-array>
        #                         ^
        self.copy_until(string_array_offset + len(string_array_tag.content))

    def _handle_plurals_tag(self, plurals_tag, plurals_offset, comment):
        # <plurals name="foo">   <item>Hello ...
        #                     ^
        self.copy_until(plurals_offset + plurals_tag.inner_offset)

        first_item_offset = None
        strings = {}
        for item_tag, item_offset in plurals_tag.find('item'):
            if item_tag.inner.strip() == "":
                strings = None
                break

            first_item_offset = first_item_offset or item_offset

            rule = self.RULES_ATOI[item_tag.attrs['quantity']]
            strings[rule] = item_tag.inner
        last_item_tag, last_item_offset = item_tag, item_offset

        if strings is not None:
            string = String(plurals_tag.attrs['name'], strings,
                            order=self._order, developer_comment=comment)
            self._order += 1

            # <plurals name="foo">   <item>Hello ...
            #                        ^
            self.copy_until(plurals_offset + first_item_offset)

            # ...</item>   </plurals>...
            #           ^
            self.add(string.template_replacement)
            self.skip(last_item_offset + len(last_item_tag.content) -
                      first_item_offset)

        else:
            string = None

        # ...</plurals> ...
        #              ^
        self.copy_until(plurals_offset + len(plurals_tag.content))

        return string

    def compile(self, template, stringset):
        resources_tag_position = template.index("<resources")
        self._stringset = stringset
        self._stringset_index = 0

        self.source = template[resources_tag_position:]
        self.destination = ""
        self.ptr = 0

        resources_tag = DumbXml(self.source)

        for tag, offset in resources_tag.find(("string", "string-array",
                                               "plurals")):
            if tag.name == "string":
                self._compile_string(tag, offset)
            elif tag.name == "string-array":
                self._compile_string_array(tag, offset)
            elif tag.name == "plurals":
                self._compile_plurals(tag, offset)
        self.copy_until(len(self.source))

        # Lets do another pass to clear empty <string-array>s
        self.source = self.destination
        self.destination = ""
        self.ptr = 0
        resources_tag = DumbXml(self.source)
        for string_array_tag, string_array_offset in resources_tag.find(
                "string-array"):
            if len(list(string_array_tag.find("item"))) == 0:
                self.copy_until(string_array_offset)
                self.skip(len(string_array_tag.content))
        self.copy_until(len(self.source))

        compiled = template[:resources_tag_position] + self.destination

        del self._stringset
        del self._stringset_index
        del self.source
        del self.destination
        del self.ptr

        return compiled

    def _compile_string(self, string_tag, string_offset):
        try:
            next_string = self._stringset[self._stringset_index]
        except IndexError:
            next_string = None
        if (next_string is not None and
                next_string.template_replacement == string_tag.inner):
            # found one to replace
            self._stringset_index += 1

            self.copy_until(string_offset + string_tag.inner_offset)
            self.add(next_string.string)
            self.skip(len(string_tag.inner))
            self.copy_until(string_offset + len(string_tag.content))

        else:
            # didn't find it, must remove by skipping it
            self.copy_until(string_offset)
            self.skip(len(string_tag.content))

    def _compile_string_array(self, string_array_tag, string_array_offset):
        self.copy_until(string_array_offset + string_array_tag.inner_offset)
        for item_tag, item_offset in string_array_tag.find("item"):
            try:
                next_string = self._stringset[self._stringset_index]
            except IndexError:
                next_string = None
            if (next_string is not None and
                    next_string.template_replacement == item_tag.inner):
                # found one to replace
                self._stringset_index += 1

                self.copy_until(string_array_offset + item_offset +
                                item_tag.inner_offset)
                self.add(next_string.string)
                self.skip(len(item_tag.inner))
                self.copy_until(string_array_offset + item_offset +
                                len(item_tag.content))

            else:
                # didn't find it, must remove by skipping it
                self.copy_until(string_array_offset + item_offset)
                self.skip(len(item_tag.content))
        self.copy_until(string_array_offset + len(string_array_tag.content))

    def _compile_plurals(self, plurals_tag, plurals_offset):
        try:
            next_string = self._stringset[self._stringset_index]
        except IndexError:
            next_string = None
        if (next_string is not None and
                next_string.template_replacement == plurals_tag.inner.strip()):
            # found one to replace, if the hash is on its own on a line with
            # only spaces, we have to remember it's indent
            self._stringset_index += 1

            hash_position = plurals_offset + plurals_tag.inner_offset +\
                plurals_tag.inner.index(next_string.template_replacement)
            indent_length = self.source[hash_position::-1].\
                index('\n') - 1
            indent = self.source[hash_position - indent_length:hash_position]
            end_of_hash = hash_position + len(next_string.template_replacement)
            tail_length = self.source[end_of_hash:].index('\n')
            tail = self.source[end_of_hash:end_of_hash + tail_length]

            if (self.SPACE_PAT.search(indent) and self.SPACE_PAT.search(tail)):
                # write until beginning of hash
                self.copy_until(hash_position - indent_length)
                for rule, value in next_string.string.items():
                    self.add(
                        indent +
                        self.plural_template.format(rule=self.RULES_ITOA[rule],
                                                    string=value) +
                        tail + '\n'
                    )

            else:
                # string is not on its own, simply replace hash with all plural
                # forms
                self.copy_until(hash_position)
                for rule, value in next_string.string.items():
                    self.add(
                        self.plural_template.format(
                            rule=self.RULES_ITOA[rule], string=value
                        )
                    )
            self.skip(indent_length + len(next_string.template_replacement) +
                      tail_length + 1)

            # finish up by copying until the end of </plurals>
            self.copy_until(plurals_offset + len(plurals_tag.content))

        else:
            # didn't find it, must remove by skipping it
            self.skip_until(plurals_offset + len(plurals_tag.content))


def main():
    test_handler(AndroidHandler, '''
        <resources>
            <string name="foo1">hello osrld</string>
            <string name="foo2">hello sssfa</string>
            <string name="foo3">hello world</string>
            <string name="foo4">hello sdiid</string>
            <string-array name="asdf">
                <item>asdf</item>
                <item>fdsa</item>
                <item>i883</item>
            </string-array>
            <plurals name="unread_messages">
                <item quantity="one">%s message</item>
                <item quantity="other">%s messages</item>
            </plurals>
        </resources>
    ''')


if __name__ == "__main__":
    main()
