#!/usr/bin/env python
# dbphoto.py
# The sqlite database access functions for the XoPhoto application
#
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
""" General introduction to XoPhoto database
Two limitations have guided the layout of the databases:
   1. Datastore is very slow reading or writing large data chunks
   2.Minimal processing horsepower makes thumbnail generation slow and suggests that
       thumbnails should be stored in the persistant data storage area assigned
       to each activity.
So there are really two sqlite databases associated with XoPhoto. xophoto.sqlite is
stored in the journal, and holds the user state information -- Album stacks are stored
in a table 'groups'. The table 'config' remembers last operations.

The much larger database 'data_cache.sqlite' is stored in the persistent data area
available to XoPhoto. I houses the thumbnail blobs and the necessary data about each
image found in the datastore.


"""
from gettext import gettext as _

import os
from  sqlite3 import dbapi2 as sqlite
from sqlite3 import *
import sqlite3
import hashlib
import time

#pick up activity globals
from xophotoactivity import *
import display

#define globals related to sqlite
sqlite_file_path = None

import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
#console_handler.setFormatter(console_formatter)
#_logger.addHandler(console_handler)


class DbAccess:
    con = None
    cursor = None
    def __init__(self,fn):
        self.opendb(fn)
        self.added = 0
        self.error = ''
    
    def opendb(self,dbfilename):
        try:
            if not os.path.isfile(dbfilename):
                _logger.debug('trying to open database cwd:%s filename %s'%(os.getcwd(),dbfilename,))
                dbfilename = os.path.join(os.getcwd(),dbfilename)
            self.con = sqlite3.connect(dbfilename)
            self.dbfilename = dbfilename
            self.con.row_factory = sqlite3.Row
            self.con.text_factory = str
            #rows generated thusly will have columns that are  addressable as dict of fieldnames
            self.cur = self.con.cursor()
            path = os.path.dirname(dbfilename)
            data_db = os.path.join(path,'data_cache.sqlite')
            sql = "attach '%s' as data_cache"%data_db
            _logger.debug('attaching using sql %s'%sql)
            self.cur.execute(sql)
        except IOError,e:
            _logger.debug('open database failed. exception :%s '%(e,))
            return None
        return self.cur
    
    def connection(self):
        #test to see if the database is open
        if self.con:
            try:
                cursor = self.con.cursor()
                cursor.execute('select * from config')
                not_open = False
            except:
                _logger.exception('sql "select * from config" failed.')
                not_open = True
        if not self.con or not_open:
            self.opendb(self.dbfilename)
        return self.con
    
    def vacuum_data_cache(self):
        if self.is_open():
            self.closedb()
        dbfilename = os.path.join(os.getcwd(),'data_cache.sqlite')
        try:
            conn = sqlite3.connect(dbfilename)
            cursor = conn.cursor()
            cursor.execute('vacuum')
            conn.commit()
            conn.close()
            self.opendb(self.dbfilename)
        except Exception,e:
            _logger.debug('vacuum error %s'%e)


    def is_open(self):
        if self.con: return True
        return False
    
    def get_error(self):
        return self.error

    def closedb(self):
        if self.con:self.con.close()
        self.con = None
        
    def restart_db(self):
        self.closedb()
        self.opendb(self.dbfilename)
        
    def get_mime_list(self):
        mime_list =[]
        conn = self.connection()
        cur = conn.cursor()
        cur.execute('select * from config where name ="mime_type"')
        rows = cur.fetchall()
        for m in rows:
            mime_list.append(m[2])
        return mime_list
    
    def get_mime_type(self,jobject_id):
        self.cur.execute("select * from data_cache.picture where jobject_id = '%s'"%jobject_id)
        rows = self.cur.fetchall()
        if len(rows) > 0:
            return rows[0]['mime_type']
        return None
    
    def get_albums(self):
        cursor = self.connection().cursor()
        cursor.execute("select * from groups where category = 'albums' order by seq asc")
        return cursor.fetchall()
    
    def get_albums_containing(self,jobject_id):
        cursor = self.connection().cursor()
        cursor.execute('select * from groups where jobject_id = ?',(jobject_id,))
        return cursor.fetchall()

    def get_album_thumbnails(self,album_id,is_journal=False):
        if is_journal: #is_journal: #want most recent first, need left join because picture may not exist yet
            #sql = """select groups.*, data_cache.picture.* from  groups left join data_cache.picture  \
                  #where groups.category = ? and groups.jobject_id = data_cache.picture.jobject_id order by groups.seq desc"""
            sql = """select groups.*, picture.* from  groups, picture where groups.category = ?
            and groups.jobject_id = picture.jobject_id order by groups.seq desc"""
        else:
            #sql = """select groups.*, data_cache.picture.* from groups left join data_cache.picture  \
                  #where groups.category = ? and groups.jobject_id = data_cache.picture.jobject_id order by groups.seq """
            sql = """select groups.*, picture.* from groups, picture  where category = ?
            and groups.jobject_id = picture.jobject_id order by seq"""
        cursor = self.connection().cursor()
        cursor.execute(sql,(str(album_id),))
        return cursor.fetchall()
    
    def get_thumbnail_count(self,album_id):
        conn = self.connection()
        cursor = conn.cursor()
        cursor.execute('select count(*) as count from groups,picture where category = ? and groups.jobject_id = picture.jobject_id',(str(album_id),))
        rows = cursor.fetchall()
        if len(rows) == 1:
            return rows[0]['count']
        else:
            return -1
        
    def update_resequence(self,id,seq):
        """ update the groups record at id, then reassign seq numbers for this album"""
        conn = self.connection()
        cur = conn.cursor()
        cur.execute('select * from groups where id = ?',(id,))
        rows = cur.fetchall()
        if len(rows) != 1:
            _logger.debug('update_resequence did not fetch id=%s'%id)
            return
        album_id = rows[0]['category']
        cur.execute("update groups set seq = ? where id = ?",(seq,id,))
        conn.commit()
        cur.execute ('select * from groups where category = ? order by seq',(album_id,))
        rows = cur.fetchall()
        if len(rows) == 0:
            _logger.debug('no group members for album_id = %s'%album_id)
            return
        #need another cursor
        update_cursor = conn.cursor()
        num = 0
        for row in rows:
            update_cursor.execute("update groups set seq = ? where id = ?",(num,row['id'],))
            num += 20
        conn.commit()  
                   
    def create_picture_record(self,object_id, fn):
        """create a record in picture pointing to unique pictures in the journal.
           Use md5 checksum to test for uniqueness
           For non unique entries, add a copy number (fieldname:duplicate) greater than 0
           returns number of records added
        """
        _logger.debug('create_picture_record object_id:%s  file: %s'%(object_id,fn,))
        start= time.clock()
        #if object_id == '': return
        
        #we'll calculate the md5, check it against any pictures, and store it away
        md5_hash = Md5Tools().md5sum(fn)
        sql = "select * from data_cache.picture where md5_sum = '%s'"%(md5_hash,)
        conn = self.connection()
        cur = conn.cursor()
        cur.execute(sql)
        rows_md5 = cur.fetchall()
        if len(rows_md5) >0:
            #pass
            _logger.debug('duplicate picture, ojbect_id %s path: %s'%(object_id,fn,))
            return 0
        sql = "select * from data_cache.picture where jobject_id = '%s'"%(object_id,)
        cur.execute(sql)
        rows = cur.fetchall()
        _logger.debug('rowcount %s object_id %s'%(len(rows),object_id))
        #the object_id is supposed to be unique, so add only new object_id's
        info = os.stat(fn)
        if len(rows) == 0:
            sql = """insert into data_cache.picture \
                  (in_ds, mount_point, orig_size, create_date,jobject_id, md5_sum) \
                  values (%s,'%s',%s,'%s','%s','%s')""" % \
                  (1, fn, info.st_size, info.st_ctime, object_id, md5_hash,)
            cursor = self.connection().cursor()
            cursor.execute(sql)                
            self.con.commit()
            _logger.debug('%s seconds to insert'%(time.clock()-start))
            return 1
        elif len(rows) == 1:
            sql = """update data_cache.picture set in_ds = ?, mount_point = ?, orig_size = ?, \
                  create_date = ?, md5_sum = ?"""
            cursor = self.connection().cursor()
            cursor.execute(sql,(1, fn, info.st_size, info.st_ctime, md5_hash,))             
            self.con.commit()            
            _logger.debug('%s seconds to update'%(time.clock()-start))
        return 0
    
    def is_picture_in_ds(self,fn):
        if not fn: return None
        md5_hash = Md5Tools().md5sum(fn)
        return self.is_md5_in_picture(md5_hash)

    def is_md5_in_picture(self,md5_hash):
        if not md5_hash: return None
        sql = "select * from data_cache.picture where md5_sum = '%s'"%(md5_hash,)
        conn = self.connection()
        cur = conn.cursor()
        cur.execute(sql)
        rows_md5 = cur.fetchall()
        if len(rows_md5) >0:
            return rows_md5[0]
        return False


    def put_ds_into_picture(self,jobject_id):
        self.cur.execute("select * from data_cache.picture where jobject_id = ?",(jobject_id,))
        rows = self.cur.fetchall()
        #_logger.debug('rowcount %s object_id %s'%(len(rows),object_id))
        #the object_id is supposed to be unique, so add only new object_id's
        if len(rows) == 0:
            cursor = self.connection().cursor()
            cursor.execute('insert into data_cache.picture (jobject_id) values (?)',(str(jobject_id),))              
            self.con.commit()
    
    def set_title_in_picture(self,jobject_id,title):
        """question: should title,comment default to last entered?"""
        if not jobject_id: return #during startup, jobject not yet set
        sql = "select * from data_cache.picture where jobject_id = '%s'"%(jobject_id,)
        cur = self.connection().cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if len(rows) == 1:
            sql = """update data_cache.picture set title = ? where jobject_id = ?"""
            cursor = self.connection().cursor()
            cursor.execute(sql,(title,jobject_id,))             
            self.con.commit()            

    def set_title_in_groups(self,jobject_id,title):
        self.set_title_in_picture(jobject_id,title)
        
    def get_title_in_picture(self,jobject_id):
        if not jobject_id: return #during startup, jobject not yet set
        sql = "select * from data_cache.picture where jobject_id = '%s'"%(jobject_id,)
        cur = self.connection().cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]['title']
        return None

    def set_comment_in_picture(self,jobject_id,comment):
        if not jobject_id: return #during startup, jobject not yet set
        sql = "select * from data_cache.picture where jobject_id = '%s'"%(jobject_id,)
        cur = self.connection().cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if len(rows) == 1:
            sql = """update data_cache.picture set comment = ? where jobject_id = ?"""
            cursor = self.connection().cursor()
            cursor.execute(sql,(comment,jobject_id,))             
            self.con.commit()            

    def set_comment_in_groups(self,jobject_id,comment):
        self.set_comment_in_picture(jobject_id,comment)
        
    def get_comment_in_picture(self,jobject_id):
        if not jobject_id: return #during startup, jobject not yet set
        sql = "select * from data_cache.picture where jobject_id = '%s'"%(jobject_id,)
        cur = self.connection().cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]['comment']
        return None

    
    def get_picture_rec_for_id(self,jobject_id):
        if not jobject_id: return #during startup, jobject not yet set
        sql = "select * from data_cache.picture where jobject_id = '%s'"%(jobject_id,)
        cur = self.connection().cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]
        return None

    def clear_in_ds(self):
        self.connection().execute('update data_cache.picture set in_ds = 0')
    
    def delete_not_in_ds(self):
        self.connection().execute('delete from data_cache.picture where in_ds = 0')

    def check_in_ds(self,fullpath,size):
        """returns true/false based upon identity of file path and image size"""
        sql = "select * from data_cache.picture where mount_point = '%s' and orig_size = %s"%(fullpath,size,)
        conn = self.connection()
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if len(rows)>0: return True
        return False

    def get_last_album(self):
        """returns the album_id (time stamp) of most recent id or None
        second parameter retured is row number for update/insert
        """
        cursor = self.connection().cursor()
        """
        try:
            cursor.execute("select * from config where name = ?",('last_album',))
        except:
            return None,0
        """
        cursor.execute("select * from config where name = ?",('last_album',))

        rows = cursor.fetchmany()
        _logger.debug('found %s last albums'%len(rows))
        if len(rows) == 1:
            return (rows[0]['value'],rows[0]['id'],)
        elif len(rows) > 1:
            _logger.debug('somehow got more than one last_album record')
            cursor.execute("delete from config where name = 'last_album'")
            self.con.commit()
        return None,0 #config is initialized with mime-types so id is > 0 if last album exists
    
    def set_last_album(self,album_id):
        cursor = self.connection().cursor()
        value,id = self.get_last_album()
        if id > 0:
            cursor.execute("update config set value = ? where id = ?",(album_id,id))
        else:
            cursor.execute("insert into config (name,value) values (?,?)",('last_album',album_id))
        self.con.commit()
        
    def set_album_count(self,album_id,count):
        cursor = self.connection().cursor()
        cursor.execute("select * from groups where category = 'albums' and subcategory = ?",(str(album_id),))
        rows = cursor.fetchmany()
        if len(rows) == 1:
            try:
                cursor.execute('update groups set stack_size = ? where id = ?',(count,rows[0]['id']))
                self.con.commit()
            except Exception,e:
                _logger.debug('set album count error:%s'%e)
        
    def get_album_count(self,album_id):
        cursor = self.connection().cursor()
        try:
            cursor.execute("select * from groups where category = 'albums' and subcategory = ?",(str(album_id,)))
            rows = cursor.fetchmany()
            if len(rows) == 1:
                return rows[0]['seq']
            return 0
        except:
            return 0
        
    def get_album_name_from_timestamp(self,timestamp):
        if not timestamp: return None
        cursor = self.connection().cursor()
        cursor.execute("select * from groups where category = 'albums' and subcategory = ?",(str(timestamp),))
        rows = cursor.fetchall()
        if len(rows) == 1:
            return rows[0]['stack_name']
        return None
        
        
    def create_update_album(self,album_id,name):
        conn = self.connection()
        cursor = conn.cursor()
        cursor.execute('select * from groups where category = ? and subcategory = ?',\
                       ('albums',str(album_id,)))
        rows = cursor.fetchmany()
        _logger.debug('create-update found %s records. album:%s. Name:%s'%(len(rows),album_id,name,))
        if len(rows)>0  : #pick up the id
            id = rows[0]['id']
            cursor.execute("update groups set  subcategory = ?, stack_name = ? where id = ?",\
                           (str(album_id),name,id))
        else:
            cursor.execute("insert into groups (category,subcategory,stack_name,seq) values (?,?,?,?)",\
                           ('albums',str(album_id),name,30))
        conn.commit()
        if len(rows)>0:
            return
        
        rows = self.get_albums()
        if len(rows)>0:
            #now go through and rewrite the sequence numbers
            #need another cursor
            update_cursor = conn.cursor()
            num = 0
            for row in rows:
                update_cursor.execute("update groups set seq = ? where id = ?",(num,row['id'],))
                num += 20
            conn.commit()
        else:
            _logger.debug('failed to get albums  for resequence in create_update_album')

    def reorder_albums(self,album_id,seq):
        conn = self.connection()
        cursor = conn.cursor()
        cursor.execute('select * from groups where category = "albums" and subcategory = ?',\
                       (str(album_id),))
        rows = cursor.fetchmany()
        _logger.debug('reorder_albums found %s records. album:%s.'%(len(rows),album_id,))
        if len(rows)>0  : #pick up the id
            id = rows[0]['id']
            cursor.execute("update groups set  seq = ? where id = ?",(seq,id))
        conn.commit()
        rows = self.get_albums()
        if len(rows)>0:
            #now go through and rewrite the sequence numbers
            #need another cursor
            update_cursor = conn.cursor()
            num = 0
            for row in rows:
                update_cursor.execute("update groups set seq = ? where id = ?",(num,row['id'],))
                num += 20
            conn.commit()
        else:
            _logger.debug('failed to get albums  for resequence in create_update_album')


    def add_image_to_album(self, album_id, jobject_id):
        cursor = self.connection().cursor()
        cursor.execute('select max(seq) as max_seq from groups where category = ? group by category',
                       (album_id,))
        rows = cursor.fetchall()
        if len(rows)>0:
            old_seq = rows[0]['max_seq']
        else:
            old_seq = 0
            _logger.debug('failed to get max of seq for album %s'%album_id)
        #we will try to add the same picture only once
        cursor.execute("select * from groups where category = ? and jobject_id = ?",\
                       (str(album_id), str(jobject_id,)))
        rows = cursor.fetchmany()
        if len(rows)>0: return None
        cursor.execute("insert into groups (category,subcategory,jobject_id,seq) values (?,?,?,?)",\
                           (str(album_id),'',str(jobject_id),old_seq + 20))
        self.con.commit()
            
    def delete_image(self, album_id, jobject_id):
        conn = self.connection()
        cursor = conn.cursor()
        cursor.execute("delete from groups where category = ? and jobject_id = ?",\
                       (str(album_id), str(jobject_id),))
        conn.commit()
    
    def write_transform(self,jobject_id,w,h,x_thumb,y_thumb,image_blob,rec_id = None,transform_type='thumb',rotate_left=0,seq=0):
        _logger.debug('write_transform for rec_id %s'%rec_id)
        if image_blob:
            thumbstr = pygame.image.tostring(image_blob,'RGB')
        else:
            thumbstr = ''
        thumb_binary = sqlite3.Binary(thumbstr)
        conn = self.connection()
        cursor = conn.cursor()
        try:
            if rec_id:
                cursor.execute("""update data_cache.transforms set thumb = ?, scaled_x = ?, scaled_y = ?, rotate_left = ?
                               where id = ?""",(thumb_binary,x_thumb,y_thumb,rotate_left,rec_id))
            else:
                cursor.execute("""insert into data_cache.transforms (jobject_id,original_x,original_y,
                               scaled_x,scaled_y,thumb,transform_type,rotate_left,seq)
values (?,?,?,?,?,?,?,?,?)""",(jobject_id,w,h,x_thumb,y_thumb,thumb_binary,transform_type,rotate_left,seq))
        except sqlite3.Error,e:
            _logger.debug('write thumbnail error %s'%e)
            return None
        conn.commit()
        
    def get_transforms(self,jobject_id):
        cursor = self.connection().cursor()
        cursor.execute('select * from data_cache.transforms where jobject_id = ?',(jobject_id,))
        rows = cursor.fetchall()
        return rows

    def delete_all_references_to(self,jobject_id):
        conn = self.connection()
        cursor = conn.cursor()
        self.delete_if_exists('groups','jobject_id',jobject_id)
        self.delete_if_exists('groups','subcategory',jobject_id)
        self.delete_if_exists('data_cache.picture','jobject_id',jobject_id)
        self.delete_if_exists('data_cache.transforms','jobject_id',jobject_id)
    
    def delete_if_exists(self,table,field,value):
        conn = self.connection()
        cursor = conn.cursor()
        sql = 'select * from %s where %s = ?'%(table, field,)
        cursor.execute(sql,(value,))
        rows = cursor.fetchall()
        if len(rows) > 0:
            try:
                sql = "delete from %s where %s = '%s'"%(table,field,str(value),)
                cursor.execute(sql)
                conn.commit()
            except Exception,e:
                _logger.error('error deleting all references for object:%s sql:%s. Error: ;%s'%(jobject_id,sql,e,))
                
    
    
    def set_config(self,name,value):
        cursor = self.connection().cursor()
        cursor.execute('select * from config where name = ?',(name,))
        rows = cursor.fetchall()
        if len(rows)>0:
            cursor.execute("update config set value = ? where id = ?",(value,rows[0]['id']))
        else:
            cursor.execute("insert into config (name,value) values (?,?)",(name,value,))
        self.con.commit()
        
    def get_config(self,name):
        cursor = self.connection().cursor()
        cursor.execute('select * from config where name = ?',(name,))
        rows = cursor.fetchall()
        if len(rows)>0:
            return rows[0]['value']
        else:
            return ''

    def set_lookup(self,name,value):
        cursor = self.connection().cursor()
        cursor.execute('select * from data_cache.lookup where name = ?',(name,))
        rows = cursor.fetchall()
        if len(rows)>0:
            cursor.execute("update data_cache.lookup set value = ? where id = ?",(value,rows[0]['id']))
        else:
            cursor.execute("insert into data_cache.lookup (name,value) values (?,?)",(name,value,))
        self.con.commit()
        
    def get_lookup(self,name):
        cursor = self.connection().cursor()
        cursor.execute('select * from data_cache.lookup where name = ?',(name,))
        rows = cursor.fetchall()
        if len(rows)>0:
            return rows[0]['value']
        else:
            return ''

    def change_album_id(self,from_id,to_id):
        if from_id == to_id: return
        conn = self.connection()
        cur = conn.cursor()
        cur.execute('select * from groups where category = ?',(from_id,))
        rows = cur.fetchall()
        if len(rows) == 0:
            _logger.debug('change_album_id did not fetch category=%s'%from_id)
            return
        #need another cursor
        update_cursor = conn.cursor()
        for row in rows:
            update_cursor.execute("update groups set category = ? where id = ?",(to_id,row['id'],))
        conn.commit()  

    def table_exists(self,table):
        try:
            sql = 'select  * from %s'%table
            self.connection().execute(sql)
            return True
        except:
            return False

    def commit(self):
        if self.con:self.con.commit()

    def set_connection(self,connection,cursor):
        self.con = connection
        self.cur = cursor

    def get_connection(self):
        """ return connection """
        return self.con

    def numberofrows(self,table):
        sql = "SELECT count(*) from %s"%table
        rows,cur = self.dbdo(sql)
        if rows:
            return rows[0][0]
        return 0

    def fieldlist(self,table):
        list=[]     #accumulator for model
        cur = self.connection().cursor()
        cur.execute('select * from %s'%table)
        if cur:
            for field in cur.description:
                list.append(field[0])
        return list
    
    def row_index(self,field,table):
        field_list = self.fieldlist(table)
        return field_list.index(field)

    def tablelist(self):
        list=[]     #accumulator for
        sql =  "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        rows,cur = self.dbdo(sql)
        if rows:
            for row in rows:
                list.append(row[0])
        return list

    def dbdo(self,sql):
        """ execute a sql statement or definition, return rows and cursor """
        try:
            cur = self.connection().cursor()
            cur.execute(sql)
            return cur.fetchall(), cur
            #self.con.commit()
        except sqlite.Error, e:            
            _logger.debug( 'An sqlite error:%s; sql:%s'%(e,sql,))
            self.error = str(e)
            raise display.PhotoException(self.error)

    def dbtry(self,sql):
        """ execute a sql statement return true if no error"""
        try:
            self.cur.execute(sql)
            return True,None
        except sqlite.Error, e:
            print sql+'\n'
            return False,e

    def upgrade_db_copy_data(self,new_db,old_db):
        try:
            conn = sqlite3.connect(new_db)
            cursor = conn.cursor()
            sql = "attach '%s' as data"%old_db
            _logger.debug('attaching using sql %s'%sql)
            cursor.execute(sql)
            old_conn = sqlite3.connect(old_db)
            old_cursor = old_conn.cursor()
        except Exception,e:
            if not os.path.isfile(new_db) or not os.path.isfile(old_db):
                _logger.debug('upgrade_db path problems new:%s old:%s'%(new_db,old_db,))
            _logger.debug('open database failed. exception :%s '%(e,))
            return False
        cursor.execute("select tbl_name from sqlite_master where type = 'table'")
        table_rows = cursor.fetchall()
        
        #get the tables in the old database
        cursor.execute("select tbl_name from data.sqlite_master where type = 'table'")
        data_rows = cursor.fetchall()
        
        for table in table_rows:
            for data_row in data_rows:
                if table[0] == data_row[0]:
                    #the two databases have the same table, continue
                    pragma_spec = 'pragma table_info(%s)'%table[0]
                    cursor.execute(pragma_spec)
                    new_fields = cursor.fetchall()

                    pragma_spec = 'pragma table_info(%s)'%table[0]
                    old_cursor.execute(pragma_spec)
                    old_fields = old_cursor.fetchall()
                    
                    #if both tables have a field, try to transfer the data                    
                    field_list = []
                    for new_field in new_fields:
                        if new_field[1] == 'id' or new_field[1] == 'rowid': continue
                        for old_field in old_fields:
                            if new_field[1] == old_field[1]:
                                field_list.append(old_field[1])
                    fields = ', '.join(field_list)
                    sql = 'insert into %s (%s) select %s from data.%s'%(table[0],fields,fields,table[0],)
                    _logger.debug('upgrade sql:%s'%sql)
                    try:
                        cursor.execute(sql)    
                    except Exception,e:
                        _logger.debug('insert into %s database failed. exception :%s '%(table[0],e,))
                        return False
                    conn.commit()
        conn.close()
        return True
        
    def get_user_version(self,path):
        try:
            conn = sqlite3.connect(path)
            cursor = conn.cursor()
        except Exception,e:
            if not os.path.isfile(path):
                _logger.debug('upgrade_db path problems new:%s old:%s'%(new_db,old_db,))
            _logger.debug('get user version. exception :%s '%(e,))
            return -1
        cursor.execute('pragma user_version')
        rows = cursor.fetchall()
        conn.close()
        if len(rows)>0:
            return rows[0][0]
        return 0
    
class Md5Tools():
    def md5sum_buffer(self, buffer, hash = None):
        if hash == None:
            hash = hashlib.md5()
        hash.update(buffer)
        return hash.hexdigest()

    def md5sum(self, filename, hash = None):
        h = self._md5sum(filename,hash)
        return h.hexdigest()
       
    def _md5sum(self, filename, hash = None):
        if hash == None:
            hash = hashlib.md5()
        try:
            fd = None
            fd =  open(filename, 'rb')
            while True:
                block = fd.read(128)
                if not block: break
                hash.update(block)
        finally:
            if fd != None:
                fd.close()
        return hash
    
    def md5sum_tree(self,root):
        if not os.path.isdir(root):
            return None
        h = hashlib.md5()
        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                h = self._md5sum(abs_path,h)
                #print abs_path
        return h.hexdigest()
    
    def set_permissions(self,root, perms='664'):
        if not os.path.isdir(root):
            return None
        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                old_perms = os.stat(abs_path).st_mode
                if os.path.isdir(abs_path):
                    new_perms = int(perms,8) | int('771',8)
                else:
                    new_perms = old_perms | int(perms,8)
                os.chmod(abs_path,new_perms)
    
if __name__ == '__main__':
    db = DbAccess('xophoto.sqlite')
    rows,cur = db.dbdo('select * from data_cache.picture')
    for row in rows:
        print row['jobject_id']
    print('index of jobject_id: %s'%db.row_index('duplicate','picture'))
    print('number of records %s'%db.numberofrows('data_cache.picture'))
    print('fields %r'%db.fieldlist('data_cache.picture'))
    print ('tables %r'%db.tablelist())
    
