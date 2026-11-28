"""Local opt-in identity storage; NOT a face detector or embedding extractor.
No camera, ROS, network or actuator access. Caller must supply embeddings from
one verified model and enforce session/safety authorization before inference.
Threshold requires model-specific validation; this module supplies no default.
"""
import contextlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid


class FaceIdentityStore:
    def __init__(self, root, *, model_sha256, dimension, threshold, max_identities=32):
        if not re.fullmatch('[0-9a-f]{64}', model_sha256):raise ValueError('model digest')
        if type(dimension)!=int or not 1<=dimension<=2048:raise ValueError('dimension')
        if type(threshold) not in (int,float) or not math.isfinite(threshold) or not 0<threshold<=1:raise ValueError('validated threshold required')
        if type(max_identities)!=int or not 1<=max_identities<=32:raise ValueError('identity quota')
        self.root=Path(root)
        if any(p.is_symlink() for p in [self.root,*self.root.parents]):raise ValueError('symlink storage')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        os.chmod(self.root,0o700)
        self.path=self.root/'identities.sqlite3'
        if self.path.is_symlink():raise ValueError('symlink database')
        self.dimension=dimension;self.threshold=threshold;self.limit=max_identities
        binding=json.dumps({'sha256':model_sha256,'dimension':dimension},sort_keys=True)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS identities (id TEXT PRIMARY KEY,name TEXT NOT NULL,vector TEXT NOT NULL,consent_time REAL NOT NULL)')
            stored=db.execute('SELECT value FROM metadata WHERE key=?',('model',)).fetchone()
            if stored is None and db.execute('SELECT COUNT(*) FROM identities').fetchone()[0]:
                raise ValueError('missing model binding for enrolled identities')
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',('model',binding))
            if db.execute('SELECT value FROM metadata WHERE key=?',('model',)).fetchone()[0]!=binding:raise ValueError('model binding mismatch')
        self.binding=binding

    @contextlib.contextmanager
    def _db(self):
        if self.path.is_symlink():raise ValueError('symlink database')
        if self.path.exists() and self.path.stat().st_size>1048576:raise ValueError('database quota')
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
        os.chmod(self.path,0o600)
        db=sqlite3.connect(self.path,timeout=1)
        try:
            if db.execute('PRAGMA page_size').fetchone()[0]!=4096:raise ValueError('unsupported database page size')
            db.execute('PRAGMA secure_delete=ON')
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA max_page_count=256') # <=1MiB at default 4096-byte pages
            db.execute('BEGIN IMMEDIATE')
            if hasattr(self,'binding'):
                row=db.execute('SELECT value FROM metadata WHERE key=?',('model',)).fetchone()
                if row is None or row[0]!=self.binding:raise ValueError('model binding missing/changed')
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def _vector(self, values):
        if not isinstance(values,(list,tuple)) or len(values)!=self.dimension:raise ValueError('embedding dimensions')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('embedding values')
        norm=math.hypot(*values)
        if not math.isfinite(norm) or norm<=0:raise ValueError('embedding norm')
        return [v/norm for v in values]

    def enroll(self, name, embedding, *, consent):
        if consent is not True:raise PermissionError('explicit subject enrollment consent required')
        if not isinstance(name,str) or not name.strip() or len(name)>64 or any(ord(c)<32 for c in name):raise ValueError('identity label')
        vector=self._vector(embedding);uid=uuid.uuid4().hex
        with self._db() as db:
            if db.execute('SELECT COUNT(*) FROM identities').fetchone()[0]>=self.limit:raise ValueError('identity quota')
            db.execute('INSERT INTO identities VALUES (?,?,?,?)',(uid,name.strip(),json.dumps(vector,allow_nan=False),time.time()))
        return uid

    def match(self, embedding, *, consent):
        if consent is not True:raise PermissionError('explicit recognition consent required')
        vector=self._vector(embedding)
        with self._db() as db:rows=db.execute('SELECT id,name,vector FROM identities').fetchall()
        matches=[]
        for uid,name,stored in rows:
            score=sum(a*b for a,b in zip(vector,self._vector(json.loads(stored))))
            if score>=self.threshold:matches.append({'identity_id':uid,'name':name,'cosine_similarity':min(1.,score)})
        # More than one enrolled identity above threshold is ambiguous, never pick one.
        return matches[0] if len(matches)==1 else None

    def list_identities(self):
        with self._db() as db:
            return [{'identity_id':uid,'name':name,'consent_time':stamp} for uid,name,stamp in db.execute('SELECT id,name,consent_time FROM identities ORDER BY consent_time')]

    def delete(self, identity_id):
        with self._db() as db:db.execute('DELETE FROM identities WHERE id=?',(identity_id,))

    def delete_all(self):
        with self._db() as db:db.execute('DELETE FROM identities')
