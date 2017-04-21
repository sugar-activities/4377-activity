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

import os
from gettext import gettext as _

import gtk
import gobject
import logging
_logger = logging.getLogger()

from sugar.activity import activity
from sugar.graphics.toolbutton import ToolButton
from help.help import Help

HOME = os.path.join(activity.get_bundle_path(), 'help/XO_Introduction.html')
#HOME = "http://website.com/something.html"
HELP_TAB = 1

class HelpTemplate(activity.Activity):
    def __init__(self, handle):
        activity.Activity.__init__(self, handle)

        #following are essential for interface to Help
        self.help_x11 = None
        self.handle = handle
        self.help = Help(self)

        self.toolbox = activity.ActivityToolbox(self)
        self.toolbox.connect_after('current_toolbar_changed',self._toolbar_changed_cb)
        self.toolbox.show()

        toolbar = gtk.Toolbar()
        self.toolbox.add_toolbar(_('Help'), toolbar)
        toolbar.show()

        label = gtk.Button('Help Template')
        label.show()
        self.set_canvas(label)

        self.set_toolbox(self.toolbox)
        self.toolbox.set_current_toolbar(0)

    def _toolbar_changed_cb(self,widget,tab_no):
        if tab_no == HELP_TAB:
            self.help_selected()
            
    def set_toolbar(self,tab):
        self.toolbox.set_current_toolbar(tab)
            
    ################  Help routines
    def help_selected(self):
        """
        if help is not created in a gtk.mainwindow then create it
        else just switch to that viewport
        """
        if not self.help_x11:
            screen = gtk.gdk.screen_get_default()
            self.pdb_window = screen.get_root_window()
            _logger.debug('xid for pydebug:%s'%self.pdb_window.xid)
            #self.window_instance = self.window.window
            self.help_x11 = self.help.realize_help()
            #self.x11_window = self.get_x11()os.geteuid()
        else:
            self.help.activate_help()
            #self.help.reshow()
            #self.help.toolbox.set_current_page(self.panes['HELP']
    
