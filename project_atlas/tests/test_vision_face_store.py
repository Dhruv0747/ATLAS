import tempfile,unittest,math
from pathlib import Path
from atlas_vision_face_store import FaceIdentityStore
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=FaceIdentityStore(Path(self.tmp.name)/'private',model_sha256='a'*64,dimension=3,threshold=.9,max_identities=2)
 def test_consent_required(self):
  with self.assertRaises(PermissionError):self.store.enroll('A',[1,0,0],consent=False)
  with self.assertRaises(PermissionError):self.store.match([1,0,0],consent=False)
 def test_match_unknown_and_delete(self):
  uid=self.store.enroll('A',[1,0,0],consent=True)
  self.assertEqual(self.store.match([1,0,0],consent=True)['identity_id'],uid)
  self.assertIsNone(self.store.match([0,1,0],consent=True))
  self.store.delete(uid);self.assertIsNone(self.store.match([1,0,0],consent=True))
 def test_missing_model_binding_rejected(self):
  import sqlite3
  self.store.enroll('A',[1,0,0],consent=True)
  with sqlite3.connect(self.store.path) as db:db.execute('DELETE FROM metadata')
  with self.assertRaises(ValueError):FaceIdentityStore(self.store.root,model_sha256='b'*64,dimension=3,threshold=.9)
  with self.assertRaises(ValueError):self.store.match([1,0,0],consent=True)
 def test_wrong_model_rejected(self):
  with self.assertRaises(ValueError):FaceIdentityStore(Path(self.tmp.name)/'private',model_sha256='b'*64,dimension=3,threshold=.9)
 def test_invalid_embeddings_rejected(self):
  for v in ([0,0,0],[1,0],[math.nan,0,1],[math.inf,0,1],[True,0,1]):
   with self.assertRaises(ValueError):self.store.enroll('A',v,consent=True)
 def test_quota_and_delete_all(self):
  self.store.enroll('A',[1,0,0],consent=True);self.store.enroll('B',[0,1,0],consent=True)
  with self.assertRaises(ValueError):self.store.enroll('C',[0,0,1],consent=True)
  self.store.delete_all();self.assertEqual(self.store.list_identities(),[])
 def test_local_private_files(self):
  import os,stat
  if os.name=='posix':
   self.assertEqual(stat.S_IMODE(self.store.root.stat().st_mode),0o700)
   self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode),0o600)
 def test_ambiguous_match_unknown(self):
  self.store.enroll('A',[1,0,0],consent=True);self.store.enroll('B',[1,0,0],consent=True)
  self.assertIsNone(self.store.match([1,0,0],consent=True))
if __name__=='__main__':unittest.main()
