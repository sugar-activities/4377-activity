#!/usr/bin/env python
#
# Copyright (C) 2009, George Hunt <georgejhunt@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import gtk
import gobject
import os
#import gconf

from sugar.graphics.toolbox import Toolbox
from sugar.graphics.xocolor import XoColor
from sugar.graphics.icon import Icon
from sugar.graphics.toolcombobox import ToolComboBox
from sugar.graphics.toolbutton import ToolButton
from gettext import gettext as _

import display

class ActivityToolbar(gtk.Toolbar):
    """The Activity toolbar with the Journal entry title, sharing,
       Keep and Stop buttons
    
    All activities should have this toolbar. It is easiest to add it to your
    Activity by using the ActivityToolbox.
    """
    def __init__(self, activity):
        gtk.Toolbar.__init__(self)

        self._activity = activity
        self._updating_share = False
        """
        activity.connect('shared', self.__activity_shared_cb)
        activity.connect('joined', self.__activity_shared_cb)
        activity.connect('notify::max_participants',
                         self.__max_participants_changed_cb)
        """
        #if activity.metadata:
        if True:
            self.label = gtk.Label(display.menu_journal_label)
            self.label.show()
            self._add_widget(self.label)

            self.title = gtk.Entry()
            self.title.set_size_request(int(gtk.gdk.screen_width() / 6), -1)
            if activity.metadata:
                self.title.set_text(activity.metadata['title'])
                #activity.metadata.connect('updated', self.__jobject_updated_cb)
            self.title.connect('changed', self.__title_changed_cb)
            self.title.connect('activate', self.__update_title_cb)
            self._add_widget(self.title)
            
            fn = os.path.join(os.getcwd(),'assets','stack_new.png')
            button = ImageButton()
            tooltip = _("Add Album Stack")
            button.set_image(fn,tip=tooltip)
            self.add_album = button
            self.add_album.show()
            self.add_album.connect('clicked', self.__add_album_clicked_cb)
            self.insert(self.add_album,-1)
            
            fn = os.path.join(os.getcwd(),'assets','stack_del.png')
            button = ImageButton()
            tooltip = _("Delete Album Stack")
            button.set_image(fn,tip=tooltip)
            button.connect('clicked', self.__delete_album_clicked_cb)
            self.insert(button,-1)

            fn = os.path.join(os.getcwd(),'assets','trash_del.png')
            button = ImageButton()
            tooltip = _("Remove Trash Images from XO")
            button.set_image(fn,tip=tooltip)
            self.empty_journal_button = button
            self.empty_journal_button.hide()
            self.empty_journal_button.connect('clicked',self.__empty_trash_clicked_cb)
            self.insert(self.empty_journal_button,-1)
        


        """
        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()
        
        self.share = ToolComboBox(label_text=_('Traceback:'))
        self.share.combo.connect('changed', self.__traceback_changed_cb)
        self.share.combo.append_item("traceback_plain", _('Plain'))
        self.share.combo.append_item('traceback_context', _('Context'))
        self.share.combo.append_item('traceback_verbose', _('Verbose'))
        self.insert(self.share, -1)
        self.share.show()

        self._update_share()
        """
        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.keep = ToolButton()
        self.keep.set_tooltip(_('Save and Start New'))
        #client = gconf.client_get_default()
        #color = XoColor(client.get_string('/desktop/sugar/user/color'))
        #keep_icon = Icon(icon_name='document-save', xo_color=color)
        keep_icon = Icon(icon_name='document-save')
        keep_icon.show()
        self.keep.set_icon_widget(keep_icon)
        #self.keep.props.accelerator = '<Ctrl>S'
        self.keep.connect('clicked', self.__keep_clicked_cb)
        self.insert(self.keep, -1)
        self.keep.show()
        
        self.stop = ToolButton('activity-stop')
        self.stop.set_tooltip(_('Stop'))
        #self.stop.props.accelerator = '<Ctrl>Q'
        self.stop.connect('clicked', self.__stop_clicked_cb)
        self.insert(self.stop, -1)
        self.stop.show()
        self._update_title_sid = None
        
    def set_label(self,text,visible=True):
        self.label.set_text(text)
        if not visible:
            self.title.set_sensitive(False)
        else:
            self.title.set_sensitive(True)
            
    def _update_share(self):
        self._updating_share = True

        if self._activity.props.max_participants == 1:
            self.share.hide()

        if self._activity.get_shared():
            self.share.set_sensitive(False)
            self.share.combo.set_active(1)
        else:
            self.share.set_sensitive(True)
            self.share.combo.set_active(0)

        self._updating_share = False
        
    def __add_album_clicked_cb (self,button):
        title = self.title.get_text()
        self._activity.activity_toolbar_add_album_cb(title)
                
    def __delete_album_clicked_cb (self,button):
        self._activity.activity_toolbar_delete_album_cb()
        
    def __empty_trash_clicked_cb(self,button):
        self._activity.activity_toolbar_empty_trash_cb()
    
    def __traceback_changed_cb(self, combo):
        model = self.share.combo.get_model()
        it = self.share.combo.get_active_iter()
        (scope, ) = model.get(it, 0)
        if scope == 'traceback_plain':
            self._activity.traceback = 'Plain'
            self._activity.debug_dict['traceback'] = 'plain'
        elif scope == 'traceback_context':
            self._activity.traceback = 'Context'        
            self._activity.debug_dict['traceback'] = 'context'
        elif scope == 'traceback_verbose':
            self._activity.traceback = 'Verbose'
            self._activity.debug_dict['traceback'] = 'verbose'
        self._activity.set_ipython_traceback()
        
    def __keep_clicked_cb(self, button):
        self._activity.save_icon_clicked = True
        self._activity.copy()

    def __stop_clicked_cb(self, button):
        self._activity.stop()

    def __jobject_updated_cb(self, jobject):
        self.title.set_text(jobject['title'])

    def __title_changed_cb(self, entry):
        if not self._update_title_sid:
            self._update_title_sid = gobject.timeout_add(
                                                1000, self.__update_title_cb)

    def __update_title_cb(self, entry=None):
        title = self.title.get_text()
        if self._activity.game.is_journal():
            self._activity.metadata['title'] = title
            self._activity.metadata['title_set_by_user'] = '1'
        else:
            self._activity.game.change_album_name(title)
            title_set_by_user = self._activity.metadata.get('title_set_by_user')
            if not title_set_by_user: #let the journal title reflect the most recent stack
                self._activity.metadata['title'] = title                
        self._update_title_sid = None
        
        return False

    def _add_widget(self, widget, expand=False):
        tool_item = gtk.ToolItem()
        tool_item.set_expand(expand)

        tool_item.add(widget)
        widget.show()

        self.insert(tool_item, -1)
        tool_item.show()

    def __activity_shared_cb(self, activity):
        self._update_share()

    def __max_participants_changed_cb(self, activity, pspec):
        self._update_share()

class ImageButton(ToolButton):
    def __init__(self):
        ToolButton.__init__(self)
        
    def set_image(self,from_file,tip=None,x=60,y=60):
            pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(from_file,x,y)
            self.image = gtk.Image()
            self.image.set_from_pixbuf(pixbuf)
            self.image.show()
            self.set_icon_widget(self.image)
            if tip:
                self.set_tooltip(tip)
            self.show()
        
class ActivityToolbox(Toolbox):
    """Creates the Toolbox for the Activity
    
    By default, the toolbox contains only the ActivityToolbar. After creating
    the toolbox, you can add your activity specific toolbars, for example the
    EditToolbar.
    
    To add the ActivityToolbox to your Activity in MyActivity.__init__() do:
    
        # Create the Toolbar with the ActivityToolbar: 
        toolbox = activity.ActivityToolbox(self)
        ... your code, inserting all other toolbars you need, like EditToolbar
        
        # Add the toolbox to the activity frame:
        self.set_toolbox(toolbox)
        # And make it visible:
        toolbox.show()
    """
    def __init__(self, activity):
        Toolbox.__init__(self)
        
        self._activity_toolbar = ActivityToolbar(activity)
        self.add_toolbar(_('Activity'), self._activity_toolbar)
        self._activity_toolbar.show()

    def get_activity_toolbar(self):
        return self._activity_toolbar


