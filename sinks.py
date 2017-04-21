#!/usr/bin/env python
# sinks.py 
#
# Copyright (C) 2010  George Hunt
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
from gettext import gettext as _

import pygame
from pygame.locals import *

from sugar.datastore import datastore
import sys, os
import gtk
import shutil
import gobject
from xml.etree.cElementTree import Element, ElementTree, SubElement

#application imports
from dbphoto import *
from sources import *
from display import *
import display

#pick up activity globals
from xophotoactivity import *

import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)

class ViewSlides():

    def __init__(self,parent):
        self._parent = parent
        self.db = None
        self.pygame_widget = None
        self.paused = False
        self.loop = True
        gobject.timeout_add(1000, self.__timeout)
        self.current_time = 1 #set so the first call of timeout will initiate action
        self.running = False
        self.paint = None
        self.is_resized = False
        self.show_title = False
        self.show_default = True
        self.is_fullscreen = False
        #display.screen.fill((0,0,0))
        #pygame.display.flip()

    def set_album_object(self,album_object):
        """ViewSlides is intstantiated at startup, before db is open, also need
        to know which album to display"""
        if not album_object: return
        self.album_object = album_object
        self.rows = album_object.rows
        self.index = album_object.thumb_index
        self.db = album_object.db
    
    def __timeout(self):
        #_logger.debug('timer tick %s'%self.current_time)
        if self.paused or not self.running:
            return True       
        self.current_time -= 1
        if self.current_time == 0:
            self.current_time = display.slideshow_dwell
            self.display_next()
        return True
            
    def display_next(self):
        self.current_time = display.slideshow_dwell
        if self.index < 0 or self.index >= len(self.rows):
            _logger.debug('display_next index out of bounds')
            return
        jobject_id = self.rows[self.index]['jobject_id']
        if not jobject_id: return

        self.paint = self.transform_scale_slide(jobject_id)
        if  self.paint:
            self.display_large()
        self.index += 1
        if self.index == len(self.rows):
            if self.loop:
                self.index = 0
            else:
                self.index -= 1
        self.album_object.thumb_index = self.index
       
    def display_large(self):
        self.album_object.large_displayed = True
        title = None
        if self.is_fullscreen:
            self.get_large_screen()
            self.title_panel.fill((0,0,0))

            title = self._parent.db.get_title_in_picture(self.rows[self.index]['jobject_id'])
            if self.show_title and title or self.show_default:
                font = pygame.font.Font(None,display.slideshow_title_font_size)
                if title:
                    show_title = title
                else:                    
                    default_title = _('Title for this Picture Will Appear Here')
                    show_title = default_title
                text = font.render('%s'%(show_title,),0,(255,255,255))
                text_rect = text.get_rect()
                text_rect.midtop =  self.title_panel.get_rect().midtop
                self.title_panel.blit(text,text_rect)
                
                comment = self._parent.db.get_comment_in_picture(self.rows[self.index]['jobject_id'])
                if comment or self.show_default:
                    self.show_default = False
                    font = pygame.font.Font(None,display.slideshow_comment_font_size)
                    if comment:
                        show_comment = comment
                    else:                    
                        default_comment = _('Use Up/Down to toggle text, space to Pause/Play, left/right for manual changes ')
                        show_comment = default_comment
                    text = font.render('%s'%(show_comment,),0,(255,255,255))
                    text_rect = text.get_rect()
                    text_rect.midbottom =  self.title_panel.get_rect().midbottom
                    self.title_panel.blit(text,text_rect)
    
            display.screen.blit(self.title_panel,(0,display.screen_h))
            _logger.debug('screen blit with title:%s'%(title,))
        display.screen.blit(self.paint,(0,0))
        pygame.display.flip()
        
    def get_large_screen(self):
        self.is_fullscreen = True
        if not self.is_resized:
            self.is_resized = True
            y = gtk.gdk.screen_height()
            size_y = y - display.screen_h
            x = gtk.gdk.screen_width()
            display.screen = pygame.display.set_mode((x,y),pygame.RESIZABLE)
            _logger.debug('title panel request:(%s,%s)'%(x,size_y,))
            self.pygame_widget = self._parent._activity._pygamecanvas.get_pygame_widget()
            if self.pygame_widget:
                self.pygame_widget.window.set_cursor(None)
            self.title_panel = pygame.Surface((x,size_y))
            self.title_panel.fill((0,0,0))

        
    def transform_scale_slide(self,jobject_id):
        """return surface transformed per database transforms,onto screen sized target"""
        _logger.debug('entered transform_scale_slide')
        if not jobject_id:
            _logger.debug('no jobject_id')    
            return None
        start = time.clock()
        rows = self.db.get_transforms(jobject_id)
        surf = None
        rotate_type_row_id = None
        row_id = None
        number_left_90s = 0
        for row in rows:
            if row['transform_type'] == 'rotate':
                if row['rotate_left']:
                    number_left_90s = row['rotate_left']
                    _logger.debug('number of 90 degree rotations:%s'%number_left_90s)
            else:
                #other transformtions go here
                pass
            
        #get the original image from the journal
        surf = self.get_picture(jobject_id)
        if not surf: return None
        display.screen.fill((0,0,0))
        if number_left_90s > 0:
            rotated_surf = pygame.transform.rotate(surf,number_left_90s * 90)
            surf = rotated_surf
        #center and scale the transformed image to the screen size
        paint = self.place_picture(surf,display.screen)        
        _logger.debug('%f seconds to rotate the slide'%(time.clock()-start))
        return paint
        
    def get_picture(self,jobject_id):
        """return picture surface from journal, given jobject_id"""
        try:
            ds_obj = datastore.get(jobject_id)
        except Exception,e:
            print('get filename from id error: %s'%e)
            return None
        if ds_obj:
            fn = ds_obj.get_file_path()
            try:
                surf = pygame.image.load(fn)
            except Exception,e:
                print('scale_image failed to load %s Exception: %s'%(fn,e))
                return None
            finally:
                ds_obj.destroy()
            return surf
        return None
        
    def place_picture(self,source,target):
        """return surface centered and scaled,but not blitted to target"""
        target_rect = target.get_rect()
        #screen_w,screen_h = target_rect.size
        screen_w,screen_h = display.screen_w,display.screen_h
        target_surf = pygame.Surface((screen_w,screen_h))
        image_rect = source.get_rect()
        screen_aspect = float(screen_w)/screen_h
        w,h = source.get_size()
        aspect = float(w)/h
        if screen_aspect < aspect: #sceen is wider than image
            x = screen_w
            y = int(x / aspect)
        else:
            y = screen_h
            x = int(y * aspect)
        _logger.debug('screen_x:%s screen_y:%s image_x:%s image_y:%s x:%s y:%s'%\
                      (screen_w,screen_h,w,h,x,y,))
        paint = pygame.transform.scale(source,(x,y))
        image_rect = paint.get_rect()

        if screen_aspect < aspect: #sceen is wider than image
            image_rect.midleft = target_rect.midleft
        else:
            image_rect.midtop = target_rect.midtop
        target_surf.blit(paint,image_rect)
        target_surf.convert()
        return target_surf
       
    def run(self):
        if len(self.rows) == 0:
            self._parent.util.alert(_('Please select a stack that contains images'),_('Cannot show a slideshow with no images'))
            self._parent._activity.use_toolbar.set_running(False)
            return
        #while self.running:
        if True:
            # Pump GTK messages.
            #while gtk.events_pending():
                #gtk.main_iteration()

            # Pump PyGame messages.
            for event in pygame.event.get():
                if event.type in (MOUSEBUTTONDOWN,MOUSEBUTTONUP,MOUSEMOTION):
                    x,y = event.pos
                if  event.type == KEYUP:
                    print event
                    if event.key == K_ESCAPE:
                        self.running = False
                    elif event.key == K_LEFT:
                        self.prev_slide()
                    elif event.key == K_RIGHT:
                        self.display_next()
                    elif event.key == K_UP:
                        self.show_title = True
                    elif event.key == K_DOWN:
                        self.show_title = False
                    elif event.key == K_SPACE:
                        self.paused = not self.paused

    def pause(self):
        self.paused = True
        
    def prev_slide(self):
        self.index = self.album_object.thumb_index 
        if self.index > 1:
            self.index -= 2
        elif self.index == 1:
            self.index = len(self.rows) - 1
        self.display_next()
        
    def next_slide(self):
        self.index = self.album_object.thumb_index 
        self.display_next()
        
    def play(self):
        self.paused = False
        self.run()
        
    def stop(self):
        self.running = False
        self.paused = False
        #'gtk.STOCK_MEDIA_STOP'
        self.album_object.large_displayed = False
        self.album_object.repaint_whole_screen()
        

class ExportAlbum():
    
    def __init__(self,parent,rows,db,base_path,path,name):
        """inputs =rows is an array or records from table xophoto.sqlite.groups
                  =db is a class object which has functions for reading database
                  =path is writeable path indicating location for new exported images
        """
        self._parent = parent
        self.rows = rows
        self.db = db
        self.sources = Datastore_SQLite(db)
        self.base_path = base_path
        self.path = path
        self.album = str(path.split('/')[-1])
        self.name = name
        self.eroot = Element('root')        
        
    def do_export(self):
        disable_write = False        
        if not os.path.isdir(self.path):
            try:
                os.makedirs(self.path)
            except:
                pass
                #fall through and use the alert in exception handler there
                #raise PhotoException('cannot create directory(s) at %s'%self.target)
        
        #check to see if we have write access to path
        try:
            fn = os.path.join(self.path,"test")
            fd = file(fn,'w')
            fd.write("this is a test")
            fd.close()
            os.unlink(fn)
        except Exception, e:
            disable_write = True
            _logger.debug('attempting to write pictures exception %s'%e)
        index = 1          
        lookup = {'image/png':'.png','image/jpg':'.jpg','image/jpeg':'.jpg','image/gif':'.gif','image/tif':'.tif'}
        ok_exts = ['png','jpg','jpeg','jpe','gif','tif',]
        for row in self.rows:
            timestamp = row['category']
            jobject_id = row['jobject_id']
            ds_object = datastore.get(jobject_id)
            if not ds_object:
                _logger.debug('failed to fetch ds object %s'%jobject_id)
                #if the picture was deleted from the datastore, we'll just ignore the error
                continue
            fn = ds_object.get_file_path()
            #mime_type = self.db.get_mime_type(jobject_id)
            mime_type = ds_object.metadata.get('mime_type','')
            #base = os.path.basename(fn).split('.')
            base = self._parent.DbAccess_object.get_title_in_picture(jobject_id)
            title = self._parent.DbAccess_object.get_title_in_picture(jobject_id)
            description = self._parent.DbAccess_object.get_comment_in_picture(jobject_id)
            #don't override a suffix that exists
            #if len(base) == 1:
            if base:
                base = base + lookup.get(mime_type,'')
                base = base.replace(' ','_')
            else:
                base = self.name + lookup.get(mime_type,'')
            base = 'img_%03d'%index +'_' + base
            _logger.debug('exporting %s to %s'%(fn,os.path.join(self.path,base),))
            cur_element = SubElement(self.eroot,base)
            if not disable_write:
                shutil.copy(fn,os.path.join(self.path,base))
            ds_object.destroy()
            
            #now update the metadata associated with this picture
            ds_object = datastore.get(jobject_id)
            md = ds_object.get_metadata()
            if md:
                if title:
                    md['title'] = title
                    cur_element.attrib['title'] = title
                if description:
                    md['description'] = description
                    cur_element.attrib['comment'] = description
                tag = md.get('tags','')
                if len(tag) == 0:
                    md['tags'] = self.album
                else:
                    if tag.find(self.album) < 0:
                        md['tags'] = md['tags']  + ', ' +self.album
                cur_element.attrib['export_dir'] = self.album
                name = self.db.get_album_name_from_timestamp(row['category'])
                if name:
                    cur_element.attrib['stack_name'] = name
                try:
                    datastore.write(ds_object)
                except Exception, e:
                    _logger.debug('datastore write exception %s'%e)
            ds_object.destroy()
            index += 1
            
            #add data from the pictue table
            pict_row = self.db.get_picture_rec_for_id(jobject_id)
            if pict_row:
                cur_element.attrib['md5'] = pict_row['md5_sum']
                cur_element.attrib['mount_point'] = pict_row['mount_point']
                cur_element.attrib['orig_size'] = str(int(pict_row['orig_size']))
                
        if not disable_write:
            cur_element = SubElement(self.eroot,'album_timestamp',)
            cur_element.text = timestamp
            fn = os.path.join(self.path,"xophoto.xml")
            ElementTree(self.eroot).write(fn)
        else:
            self._parent.game.util.alert(_('Write permission not set for path ')+
            '%s'%self.base_path+
            _(' Please see help for instructions to correct this problem.'),
            _('Cannot Write Pictures'))
                        
