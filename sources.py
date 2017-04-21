#!/usr/bin/env python
# sources.py 
#
# Copyright (C) 2010  George Hunt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Frjur option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""
Notes to myself:
the problem I'm trying to address is latency during start up.
If there is database corruption, we need to start over with empty databases
(similar to the first download of the application)
What's the best I can do?
If there are very many images in the Journal, the best I can do is a directed find
of all the appropriate mime_types in Journal, then bring up the UI, and paint the
thumbnail as each is generated.

"""
from gettext import gettext as _

from sugar.datastore import datastore
import sys, os
import gtk
import shutil
import sqlite3
import time
from xml.etree.cElementTree import Element, ElementTree, SubElement

from dbphoto import *
import display
#pick up activity globals
from xophotoactivity import *
import xophotoactivity



import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
#console_handler.setFormatter(console_formatter)
#_logger.addHandler(console_handler)
"""
Notes to myself:
need a new structure which records the ds object_ids quickly
then a routine which creates at least n thumbnails, and
another routine which will create a single thumbnail and store it- called from gtk idle loop
"""

class Datastore_SQLite():
    """class for interfacing between the Journal and an SQLite database"""
    def __init__(self,database_access_object):
        """receives an open dbaccess object (defined in dbphoto) """
        #self.db = dbaccess(fn)
        self.db = database_access_object
        self.datastore_to_process = None
        self.datastore_process_index = -1
    
    def ok(self):
        if self.db.is_open():return True
        return False
    
    def scan_images(self):
        """
        returns a list of journal object ids that have mime_type equal to one
        of the entries in mimetype table of xophoto database. 
        """
        rtn = 0
        mime_list = self.db.get_mime_list()
        (results,count) = datastore.find({})
        for f in results:
            dict = f.get_metadata().get_dictionary()
            if dict["mime_type"] in mime_list:
                #record the id, file size, file date, in_ds
                self.db.create_picture_record(f.object_id, f.get_file_path())
                rtn += 1
            f.destroy()
        self.db.commit()
        _logger.debug('%s entries found in journal. Number of pictures %s'%(count,rtn,))
        return rtn

    def check_for_recent_images(self):
        """scans the journal for pictures that are not in database, records jobject_id if found in
        table groups with the journal id in category. Can be faster because we don't have to fetch file itself.
        """
        ds_list = []
        num_found = 0
        mime_list = ['image/jpg','image/png','image/jpeg','image/gif',]
        
        #build 650 doesn't seem to understand correctly the dictionary with a list right hand side
        info = xophotoactivity.sugar_version()
        if len(info)>0:
            (major,minor,micro,release) = info
            _logger.debug('sugar version major:%s minor:%s micro:%s release:%s'%info)
        else:
            _logger.debug('sugar version failure')
            minor = 70
        if minor > 80:
            (results,count) = datastore.find({'mime_type': ['image/jpeg','image/jpg', 'image/png','image/gif']})
        else:
            (results,count) = datastore.find({'mime_type': 'image/jpeg'})
            ds_list.extend(results)
            num_found += count            
            (results,count) = datastore.find({'mime_type': 'image/jpg'})
            ds_list.extend(results)
            num_found += count
            (results,count) = datastore.find({'mime_type': 'image/png'})
            ds_list.extend(results)
            num_found += count
            (results,count) = datastore.find({'mime_type': 'image/gif'})
        ds_list.extend(results)
        num_found += count
        
        _logger.debug('Journal/datastore entries found:%s'%num_found)
        added = 0
        a_row_found = False
        cursor = self.db.connection().cursor()
        journal_list = []
        for ds in ds_list:
            #at least for now assume that the newest images are returned first
            if not a_row_found:
                journal_list.append(ds.object_id)
                dict = ds.get_metadata().get_dictionary()
                if dict["mime_type"] in mime_list:
                    cursor.execute('select * from groups where category = ? and jobject_id = ?',\
                                   (display.journal_id,str(ds.object_id),))
                    rows = cursor.fetchall()
                    if len(rows) == 0:
                        #may need to add date entered into ds (create date could be confusing)
                        self.db.put_ds_into_picture(ds.object_id)
                        self.db.add_image_to_album(display.journal_id,ds.object_id)
                        added += 1
                    else: #assume that pictures are returned in last in first out order
                        #no longer true since we are getting each mime_type separately (build 650 kludge)
                        #a_row_found = True
                        pass
            ds.destroy()
        #now go through albums and remove references that are no longer in datastore
        #cursor.execute('select * from groups')
        _logger.debug('scan found %s. Added %s datastore object ids from datastore to picture'%(count,added,))
        return (num_found,added,)
    
    def make_one_thumbnail(self):
        if not self.db.is_open(): return
        if not self.datastore_to_process:
            cursor = self.db.get_connection().cursor()
            cursor.execute('select * from picture where md5_sum = null')
            self.datastore_to_process = cursor.fetchall()
            self.datastore_process_index = 0
        if self.datastore_to_process and self.datastore_process_index > -1:
            jobject_id = self.datastore_to_process[self.datastore_process_index]['jobject_id']
            fn =get_filename_from_jobject_id(jobject_id)
            if fn:
                self.db.create_picture_record(f.object_id, fn)
                self.datastore_process_index += 1
                if self.datastore_process_index > len(self.datastore_to_process):
                    self.datastore_process_index = -1
        return True #we want to continue to process in gtk_idle_loop
        
    def get_filename_from_jobject_id(self, id):
        try:
            ds_obj = datastore.get(id)
        except Exception,e:
            _logger.debug('get filename from id error: %s'%e)
            return None
        if ds_obj:
            fn = ds_obj.get_file_path()
            ds_obj.destroy()
            return(fn)
        return None

    def delete_jobject_id_from_datastore(self,jobject_id):
        try:
            datastore.delete(jobject_id)
        except Exception,e:
            _logger.debug('delete_jobject_id_from_datastore error: %s'%e)
    
    def update_metadata(self,jobject_id,**kwargs):
        try:
            ds_obj = datastore.get(jobject_id)
        except Exception,e:
            _logger.debug('update metadata error: %s'%e)
            return None
        if ds_obj:
            md = ds_obj.get_metadata()
            if md:
                for key in kwargs.keys():
                    md[key] = kwargs[key]
                try:
                    datastore.write(ds_obj)
                except Exception, e:
                    _logger.debug('datastore write exception %s'%e)
            else:
                _logger.error('no metadata recovered from journal')
        else:
            _logger.error('no jobject returned from datastore.get()')
            
class FileTree():
    def __init__(self,db,activity):
        self.db = db
        self._activity = activity
        self.dialog = None

    def get_path(self,get_dir=False):
        _logger.debug('dialog to get user path for importing into journal')
        path = '/home/olpc/Pictures'
        try:
            os.makedirs(path)
        except:
            pass
        if get_dir:
            action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
        else:
            action = gtk.FILE_CHOOSER_ACTION_OPEN
        dialog = gtk.FileChooserDialog("Select Folder..",
                                       None,
                                       action,
                                       (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                        gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        #dialog.set_current_folder(os.path.dirname(self.last_filename))       
        dialog.set_current_folder('/home/olpc/Pictures')
        dialog.set_select_multiple(True)
        filter = gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        dialog.add_filter(filter)
        
        filter = gtk.FileFilter()
        filter.set_name("Pictures")
        filter.add_pattern("*.png,*.jpg,*jpeg,*.gif")
        dialog.add_filter(filter)
               
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            _logger.debug('%s selected'%dialog.get_filename() )
            if get_dir:
                fname = [dialog.get_filename(),]
            else:    
                fname = dialog.get_filenames()
            fname = fname
            self.last_filename = fname
        elif response == gtk.RESPONSE_CANCEL:
            fname = []
            _logger.debug( 'File chooseer closed, no files selected')
        dialog.hide()
        dialog.destroy()
        return fname
    
    def _response_cb(self,alert,response):
        self._activity.remove_alert(alert)
        if response == gtk.RESPONSE_CANCEL:
            self.cancel = True


    def copy_tree_to_ds(self,path):
        _logger.debug('copy tree received path:%s'%(path,))
        dirlist = os.listdir(path)
        abs_fn_list = []
        for fn in dirlist:
            abs_fn_list.append(os.path.join(path,fn))            
        return_val = self.copy_list_to_ds(abs_fn_list)
        return return_val
        
    def copy_list_to_ds(self,file_list):
        """receives list of absolute file names to be copied to datastore"""
        self.file_list = file_list
        reserve_at_least = 50000000L  #don't fill the last 50M of the journal
        #reserve_at_least = 5000000000L  #force it to complain for testing
        self.cancel = False
        self.proc_start = time.clock()
        if len(file_list) == 0: return
        
        #is the requested set of images going to fit in the XO datastore?
        tot = 0.0
        acceptable_extensions = ['jpg','jpeg','png','gif','jpe','tif']
        for filename in file_list:            
            chunks = filename.split('.')
            ext = ''
            if len(chunks)>1:
                ext = chunks[-1]
            if ext in acceptable_extensions:
                file_info = os.stat(filename)
                tot += file_info.st_size                
        info = os.statvfs(file_list[0])
        free_space = info.f_bsize * info.f_bavail
        #does it fit?
        if tot > free_space - reserve_at_least:   #don't fill the last 50M of the journal
            message1 = _('Selected images total ')
            message2 = _(' Megabytes but available memory is only ')
            message = message1 + '%.2f'%(tot / 1000000) + message2 + str((free_space - reserve_at_least) // 1000000)
            title = _('Please select a smaller number of images for import.')
            self._activity.util.confirmation_alert(message,title=title,confirmation_cb =self.do_import_cb)
            _logger.debug('total free space message:%s free space:%d tot:%d'%(message,free_space,tot,))
            return False
        imported = self.do_import()
        return imported
    
    def do_import_cb(self, alert,response):
        imported = self.do_import()
        return imported
    
    def do_import(self):
        #let the user know progress of the import
        added = 0
        jobject_id_list = {}
        num = len(self.file_list)
        
        #is there a xml information file in the directory where these photos are stored?
        base = os.path.dirname(self.file_list[0])  #make assumption that list is all in a single directory
        xml_path =  os.path.join(base,'xophoto.xml')
        if os.path.isfile(xml_path):
            xml_data = self.get_xml(xml_path)
            num -= 1
        else:
            xml_data = None        
        message = _('Number of images to copy to the XO Journal: ') + str(num)
        pa_title = _('Please be patient')
        alert = display.ProgressAlert(msg=message,title=pa_title)
        self._activity.add_alert(alert)
        alert.connect('response',self._response_cb)
        
        for filename in self.file_list:            
            start = time.clock()
            mtype = ''
            chunks = filename.split('.')
            if len(chunks)>1:
                ext = chunks[-1]
                if ext == 'jpg' or ext == 'jpeg' :
                    mtype = 'image/jpeg'
                elif ext == 'gif':
                    mtype = 'image/gif'
                elif ext == 'png':
                    mtype = 'image/png'
            if mtype == '': continue        
            #info = os.stat(filename)
            #size = info.st_size
            
            #check if this image md5_sum is already loaded
            if xml_data:
                found = xml_data.findall(os.path.basename(filename))
                if found:
                    md5 = found[0].attrib.get('md5_sum',None)
                    md5_row = self.db.is_md5_in_picture(md5)
                    if md5  and md5_row:
                        _logger.debug('md5 match from xml to picture table')
                        jobject_id_list[filename] = md5_row['jobject_id']
                        continue
                    
            #if the md5_sum is already in ds, abort
            md5_row = self.db.is_picture_in_ds(filename)
            if md5_row:
                jobject_id_list[filename] = md5_row['jobject_id']
                continue
            
            ds = datastore.create()
            ds.metadata['filename'] = filename
            ds.metadata['title'] = os.path.basename(filename)
            ds.metadata['mime_type'] = mtype
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'instance',os.path.basename(filename))
            shutil.copyfile(filename,dest)
            ds.set_file_path(dest)
            datastore.write(ds,transfer_ownership=True)
            self.db.create_picture_record(ds.object_id,filename)
            jobject_id_list[filename] = ds.object_id
            ds.destroy()
            _logger.debug('writing one image to datastore took %f seconds'%(time.clock()-start))
            added += 1
            alert.set_fraction(float(added)/num)
            while gtk.events_pending():
                gtk.main_iteration()
            if self.cancel:
                break
        
        #create an album for this import
        self.create_album_for_import(self.file_list,xml_data,jobject_id_list)
        
        _logger.debug('writing all images to datastore took %f seconds'%(time.clock()-self.proc_start))
        self._activity.remove_alert(alert)
        return added #non zero means True
    
    def dict_dump(self,dct):
        ret = ''
        for key in dct.keys():
            ret += '%s:%s | '%(key,dct[key])
        return ret
    
    def create_album_for_import(self,file_list,xml_data,jobject_id_list):
        _logger.debug('create album for import received jobject list %s'%self.dict_dump(jobject_id_list))
        timestamp = None
        name = None
        if xml_data:
            found = xml_data.findall('album_timestamp')
            if found:
                timestamp = found[0].text
            if timestamp == display.journal_id or timestamp == display.trash_id:
                timestamp = None
        if not timestamp:
            timestamp = str(datetime.datetime.today())
        _logger.debug('timestamp:%s'%timestamp)
        for file_name in file_list:
            jobject_id = jobject_id_list.get(file_name)
            self.db.add_image_to_album(timestamp,jobject_id)
            if xml_data:
                found = xml_data.findall(os.path.basename(file_name))
                if found:
                    _logger.debug('create album xml data %s'%self.dict_dump(found[0].attrib))
                    title = found[0].attrib.get('title')
                    if title:
                        self.db.set_title_in_groups(jobject_id,title)
                    comment = found[0].attrib.get('comment')
                    if comment:
                        self.db.set_comment_in_groups(jobject_id,comment)
                    name = found[0].attrib.get('stack_name')
        if not name:
            name = _('Camera Roll')        
        self.db.create_update_album(timestamp,name)
        self._activity.game.album_collection.album_objects[timestamp] = \
                display.OneAlbum(self.db,timestamp,self._activity.game.album_collection)
        #set the image on the top of the stack to the last one in the seqence
        self._activity.game.album_collection.album_objects[timestamp].set_top_image(jobject_id)
        #save off the unique id(timestamp)as a continuing target
        self.db.set_last_album(timestamp)
        
    def get_xml(self,xml_path):
        try:
            tree = ElementTree(file=xml_path).getroot()
        except Exception,e:
            _logger.debug('get_xml parse error: %s'%e)
            return None
        return tree

if __name__ == '__main__':
    db = DbAccess('/home/olpc/.sugar/default/org.laptop.XoPhoto/data/xophoto.sqlite')
    if db.is_open():
        ds_sql = Datastore_SQLite(db)
        #count = ds_sql.scan_images()
        count,added = ds_sql.check_for_recent_images()
        exit()
        for i in imagelist:
            print('\n%s'%ds.get_filename_from_jobject_id(i))
        ft = FileTree('xophoto.sqlite')
        #new = ft.fill_ds()
        print('%s datastore records added'%new)
    else:
        print('xophoto sqlite database failed to open')
