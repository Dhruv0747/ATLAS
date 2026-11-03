"""Mux-only file transaction. Caller owns the transaction lock and service quiescence.

There are no process or systemd operations here. The caller supplies its continuous
supervision/deadline check, also when resuming cleanup in a fresh process.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

MUX = 'atlas_cmd_vel_mux.py'
HELPER = 'atlas_source_provenance.py'
UNIT = 'atlas-cmd-vel-mux.service'
ARCHIVE = 'publisher-mux-provenance-prep-20261102.tar.gz'
ARCHIVE_SHA = '7b24c8792f7a93474be85c7f8c969be225ed9699f78b5c6b3d7bf66657296514'
MANIFEST_SHA = 'e074a40f881a70066b69cb7f8618a77278ad2b35176258735ffd06f004214063'


class Conflict(ValueError):
    """Unreviewed bytes, metadata or ownership. Preserve them for inspection."""


def require(condition, reason):
    if not condition:
        raise Conflict(reason)


def read(path):
    require(path.resolve() == path.absolute(), 'symlink in path: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'non-regular input: ' + str(path))
        data = stream.read(1024 * 1024 + 1)
        require(len(data) <= 1024 * 1024, 'unexpected input size')
        return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def identity(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), 'unexpected destination type: ' + str(path))
    return [info.st_dev, info.st_ino]


def exclusive_file(path, data, mode, timestamp=None):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        if timestamp is not None:
            os.utime(stream.fileno(), ns=(timestamp, timestamp))
        os.fsync(stream.fileno())


class MuxFiles:
    def __init__(self, staged_mux_dir, transaction_dir, live_scripts_dir):
        self.stage, self.tx, self.live = map(Path, (staged_mux_dir, transaction_dir, live_scripts_dir))
        self.work = self.tx / 'mux-files'
        self.intent = self.work / 'intent.json'

    @property
    def binding(self):
        """Sealed package binding: publisher bytes/metadata and reviewed unit configuration.

        Pinned through the reviewed manifest (MANIFEST_SHA), not a separate hard-coded hash.
        Its boot/PID fields are historical; per-boot identity comes from mux_attempt_binding.
        """
        manifest = read(self.stage / 'SHA256SUMS')
        require(sha(manifest) == MANIFEST_SHA, 'manifest drift')
        pins = dict((name, digest) for digest, name in (line.split('  ') for line in manifest.decode('ascii').splitlines()))
        data = read(self.stage / 'binding.json')
        require(sha(data) == pins.get('binding.json'), 'binding drift')
        return json.loads(data)

    def _package(self, check):
        check()
        require(sha(read(self.stage.parent / ARCHIVE)) == ARCHIVE_SHA, 'archive drift')
        manifest = read(self.stage / 'SHA256SUMS')
        require(sha(manifest) == MANIFEST_SHA, 'manifest drift')
        result = {}
        for line in manifest.decode('ascii').splitlines():
            check()
            expected, name = line.split('  ')
            path = self.stage / name
            data = read(path)
            require(sha(data) == expected and stat.S_IMODE(path.stat().st_mode) == 0o644,
                    'staged member drift: ' + name)
            result[name] = data
        result["SHA256SUMS"] = manifest
        return result

    def _original(self, package, path=None):
        meta = json.loads(package['binding.json'])['files'][MUX]
        path = self.live / MUX if path is None else path
        require(read(path) == package['rollback/' + MUX], 'original publisher bytes drift')
        info = path.stat()
        require((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_mtime_ns) ==
                (meta['uid'], meta['gid'], meta['mode'], meta['mtime_ns']), 'original metadata drift')
        require(not meta['xattrs'] and not os.listxattr(path), 'unexpected original extended attributes')
        return meta

    def verify_original(self, check):
        package = self._package(check)
        self._original(package)
        require(not os.path.lexists(self.live / HELPER), 'helper must be absent')
        check()

    def _write_intent(self, check):
        package = self._package(check)
        meta = self._original(package)
        require(not os.path.lexists(self.live / HELPER), 'helper must be absent')
        require(self.tx.resolve() == self.tx.absolute() and self.live.resolve() == self.live.absolute(), 'directory symlink')
        require(self.live.stat().st_dev == self.tx.stat().st_dev, 'atomic install requires same filesystem')
        require((os.geteuid(), os.getegid()) == (meta['uid'], meta['gid']), 'ownership mismatch')
        require(not os.path.lexists(self.work), 'file transaction already consumed')
        self.work.mkdir(mode=0o700)
        sync_dir(self.tx)
        exclusive_file(self.work / "binding.json", package["binding.json"], 0o600)
        exclusive_file(self.work / "SHA256SUMS", package["SHA256SUMS"], 0o600)
        paths = {'helper': self.work/'helper', 'replacement': self.work/'replacement', 'backup': self.work/'backup'}
        for key, data, mode, stamp in (
            ('helper', package['payload/' + HELPER], 0o644, None),
            ('replacement', package['payload/' + MUX], meta['mode'], None),
            ('backup', package['rollback/' + MUX], meta['mode'], meta['mtime_ns']),
        ):
            check()
            path = paths[key]
            exclusive_file(path, data, mode, stamp)
            require(read(path) == data and not os.listxattr(path), 'prepared file mismatch')
        # All publish/restore links exist before intent. No live path changes until
        # this journal is durable. A crash before it leaves only scratch evidence.
        os.link(paths['replacement'], self.work / 'publish-link')
        os.link(paths['backup'], self.work / 'restore-link')
        ids = {name: identity(path) for name, path in paths.items()}
        ids['times'] = {key: path.stat().st_mtime_ns for key, path in paths.items()}
        ids['original'] = identity(self.live / MUX)
        ids['live_directory'] = [self.live.stat().st_dev,self.live.stat().st_ino]
        self._check_prepared(ids, package)
        exclusive_file(self.work / 'intent.prepared', json.dumps(ids).encode(), 0o600)
        os.link(self.work / 'intent.prepared', self.intent)
        sync_dir(self.work)
        return package, ids

    def install(self, check):
        package, ids = self._write_intent(check)
        check()
        self._check_prepared(ids, package)
        os.link(self.work / 'helper', self.live / HELPER)  # exclusive, no clobber
        sync_dir(self.live)
        check()
        self._original(package)
        require(identity(self.live/MUX) == ids['original'], 'original publisher replaced')
        self._check_prepared(ids, package)
        require(identity(self.work/'publish-link') == ids['replacement'], 'publish link replaced')
        os.replace(self.work / 'publish-link', self.live / MUX)
        sync_dir(self.live)
        sync_dir(self.work)
        self.verify_installed(check)

    def _journal(self):
        ids = json.loads(read(self.intent))
        require(ids['live_directory'] == [self.live.stat().st_dev, self.live.stat().st_ino], 'live directory replaced')
        for key in ('helper', 'replacement', 'backup'):
            require(ids[key] == identity(self.work/key), 'scratch ownership mismatch')
        return ids

    def _check_prepared(self, ids, package):
        # Linux may inherit a directory group or a default ACL on new files.
        # Verify actual descriptor metadata before any production link/rename.
        meta = self._original(package, self.work / 'backup')
        for key, mode, member in (('helper', 0o644, HELPER), ('replacement', meta['mode'], MUX)):
            path = self.work / key
            info = path.stat()
            require((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_mtime_ns) ==
                    (meta['uid'], meta['gid'], mode, ids['times'][key]), 'candidate metadata drift')
            require(not os.listxattr(path) and read(path) == package['payload/' + member], 'candidate drift')

    def _rollback_package(self):
        # The staged copy may be lost after activation. Cleanup uses only durable
        # transaction-owned files, independently pinned to the reviewed manifest.
        manifest = read(self.work / 'SHA256SUMS')
        require(sha(manifest) == MANIFEST_SHA, 'rollback manifest drift')
        pins = {name: digest for digest, name in (line.split('  ') for line in manifest.decode().splitlines())}
        out = {}
        for member, stored in (('binding.json','binding.json'),('rollback/'+MUX,'backup'),
                               ('payload/'+MUX,'replacement'),('payload/'+HELPER,'helper')):
            data = read(self.work / stored)
            require(sha(data) == pins[member], 'rollback evidence drift: ' + member)
            out[member] = data
        return out

    def verify_installed(self, check):
        package = self._package(check)
        ids = self._journal()
        self._check_prepared(ids, package)
        for filename, key in ((MUX,'replacement'), (HELPER,'helper')):
            path = self.live / filename
            require(identity(path) == ids[key] and read(path) == package['payload/' + filename], 'installed file mismatch')
        check()

    def rollback(self, check):
        check()
        if not os.path.lexists(self.intent):
            # Missing journal alone cannot certify that no live mutation occurred.
            self.verify_original(check)
            return
        package = self._rollback_package()
        ids = self._journal()
        self._check_prepared(ids, package)
        dest, helper = self.live / MUX, self.live / HELPER
        if os.path.lexists(helper):
            require(identity(helper) == ids['helper'] and read(helper) == package['payload/' + HELPER], 'foreign helper')
        current = identity(dest)
        if current == ids['replacement']:
            require(read(dest) == package['payload/' + MUX], 'publisher modified since installation')
            link = self.work / 'restore-link'
            require(identity(link) == ids['backup'] and read(link) == package['rollback/' + MUX], 'rollback backup mismatch')
            check()
            require(identity(dest) == ids['replacement'], 'publisher replaced during cleanup')
            os.replace(link, dest)
            sync_dir(self.live)
            sync_dir(self.work)
        else:
            require(current in (ids['original'], ids['backup']), 'foreign publisher')
        self._original(package)
        if os.path.lexists(helper):
            check()
            require(identity(helper) == ids['helper'], 'helper replaced during cleanup')
            helper.unlink()
            sync_dir(self.live)
        self._original(package)
        require(not os.path.lexists(helper), "helper removal failed")
        check()
