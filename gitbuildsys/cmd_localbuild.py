#!/usr/bin/python -tt
# vim: ai ts=4 sts=4 et sw=4
#
# Copyright (c) 2012 Intel, Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; version 2 of the License
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc., 59
# Temple Place - Suite 330, Boston, MA 02111-1307, USA.

"""Implementation of subcmd: localbuild
"""

import os
import tempfile
import glob
import subprocess
import urlparse

import msger
import utils
import errors
from conf import configmgr

from gbp.scripts.buildpackage_rpm import git_archive
from gbp.pkg import compressor_aliases
from gbp.rpm.git import GitRepositoryError, RpmGitRepository
import gbp.rpm as rpm

change_personality = {
            'i686':  'linux32',
            'i586':  'linux32',
            'i386':  'linux32',
            'ppc':   'powerpc32',
            's390':  's390',
            'sparc': 'linux32',
            'sparcv8': 'linux32',
          }

obsarchmap = {
            'i686':     'i586',
            'i586':     'i586',
          }

buildarchmap = {
            'i686':     'i686',
            'i586':     'i686',
            'i386':     'i686',
          }

supportedarchs = [
            'x86_64',
            'i686',
            'i586',
            'armv7hl',
            'armv7el',
            'armv7tnhl',
            'armv7nhl',
            'armv7l',
          ]

OSCRC_TEMPLATE = """[general]
apiurl = %(apiurl)s
plaintext_passwd=0
use_keyring=0
http_debug = %(http_debug)s
debug = %(debug)s
gnome_keyring=0
[%(apiurl)s]
user=%(user)s
passx=%(passwdx)s
"""

APISERVER   = configmgr.get('build_server', 'build')
USER        = configmgr.get('user', 'build')
PASSWDX     = configmgr.get('passwdx', 'build')
TMPDIR      = configmgr.get('tmpdir')

def do(opts, args):

    workdir = os.getcwd()
    if len(args) > 1:
        msger.error('only one work directory can be specified in args.')
    if len(args) == 1:
        workdir = args[0]


    hostarch = utils.get_hostarch()
    buildarch = hostarch
    if opts.arch:
        if opts.arch in buildarchmap:
            buildarch = buildarchmap[opts.arch]
        else:
            buildarch = opts.arch
    if not buildarch in supportedarchs:
        msger.error('arch %s not supported, supported archs are: %s ' % \
                   (buildarch, ','.join(supportedarchs)))

    specs = glob.glob('%s/packaging/*.spec' % workdir)
    if not specs:
        msger.error('no spec file found under /packaging sub-directory')

    specfile = specs[0] #TODO:
    if len(specs) > 1:
        msger.warning('multiple specfiles found.')


    tmpdir = '%s/%s' % (TMPDIR, USER)
    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)

    oscrc = OSCRC_TEMPLATE % {
                "http_debug": 1 if msger.get_loglevel() == 'debug' else 0,
                "debug": 1 if msger.get_loglevel() == 'verbose' else 0,
                "apiurl": APISERVER,
                "user": USER,
                "passwdx": PASSWDX,
            }
    (fd, oscrcpath) = tempfile.mkstemp(dir=tmpdir,prefix='.oscrc')
    os.close(fd)
    f = file(oscrcpath, 'w+')
    f.write(oscrc)
    f.close()

    distconf = configmgr.get('distconf', 'localbuild')
    if opts.dist:
        distconf = opts.dist

    # get dist build config info from OBS prject.
    bc_filename = None
    if distconf is None:
        msger.error('no dist config specified, see: gbs localbuild -h.')
        """
        msger.info('get build config file from OBS server')
        bc_filename = '%s/%s.conf' % (tmpdir, name)
        bs = buildservice.BuildService(apiurl=APISERVER, oscrc=oscrcpath)
        prj = 'Trunk'
        arch = None
        for repo in bs.get_repos(prj):
            archs = bs.get_ArchitectureList(prj, repo.name)
            if buildarch in obsarchmap and obsarchmap[buildarch] in archs:
                arch = obsarchmap[buildarch]
                break
            for a in archs:
                if msger.ask('Get build conf from %s/%s, OK? '\
                             % (repo.name, a)):
                    arch = a
        if arch is None:
            msger.error('target arch is not correct, please check.')

        bc = bs.get_buildconfig('Trunk', arch)
        bc_file = open(bc_filename, 'w')
        bc_file.write(bc)
        bc_file.flush()
        bc_file.close()
        distconf = bc_filename
        """

    need_root = True # TODO: kvm don't need root.

    build_cmd  = configmgr.get('build_cmd', 'localbuild')
    build_root = configmgr.get('build_root', 'localbuild')
    if opts.buildroot:
        build_root = opts.buildroot
    cmd = [ build_cmd,
            '--root='+build_root,
            '--dist='+distconf,
            '--arch='+buildarch ]
    build_jobs = utils.get_processors()
    if build_jobs > 1:
        cmd += ['--jobs=%s' % build_jobs]
    if opts.clean:
        cmd += ['--clean']
    if opts.debuginfo:
        cmd += ['--debug']

    if opts.repositories:
        for repo in opts.repositories:
            cmd += ['--repository='+repo]
    else:
        msger.error('No package repository specified.')

    if opts.noinit:
        cmd += ['--noinit']
    cmd += [specfile]

    if need_root:
        sucmd = configmgr.get('su-wrapper', 'localbuild').split()
        if sucmd[0] == 'su':
            if sucmd[-1] == '-c':
                sucmd.pop()
            cmd = sucmd + ['-s', cmd[0], 'root', '--' ] + cmd[1:]
        else:
            cmd = sucmd + cmd

    if hostarch != buildarch and buildarch in change_personality:
        cmd = [ change_personality[buildarch] ] + cmd;

    msger.info(' '.join(cmd))

    if buildarch.startswith('arm'):
        try:
            utils.setup_qemu_emulator()
        except errors.QemuError, e:
            msger.error('%s' % e)

    spec = rpm.parse_spec(specfile)
    if not spec.name or not spec.version:
        msger.error('can\'t get correct name or version from spec file.')

    urlres = urlparse.urlparse(spec.orig_file)

    tarball = 'packaging/%s' % os.path.basename(urlres.path)
    msger.info('generate tar ball: %s' % tarball)
    try:
        repo = RpmGitRepository(workdir)
    except GitRepositoryError:
        msger.error("%s is not a git repository" % (os.path.curdir))

    comp_type = compressor_aliases.get(spec.orig_comp, None)
    if not git_archive(repo, spec, "%s/packaging" % workdir, 'HEAD', comp_type,
                       comp_level=9, with_submodules=True):
        msger.error("Cannot create source tarball %s" % tarball)
 
    # runner.show() can't support interactive mode, so use subprocess insterad.
    try:
        rc = subprocess.call(cmd)
        if rc:
            msger.error('rpmbuild fails')
        else:
            msger.info('The buildroot was: %s' % build_root)
            msger.info('Done')
    except KeyboardInterrupt, i:
        msger.info('keyboard interrupt, killing build ...')
        subprocess.call(cmd + ["--kill"])
        msger.error('interrrupt from keyboard')
    finally:
        os.unlink("%s/%s" % (workdir, tarball))
        os.unlink(oscrcpath)
        if bc_filename:
            os.unlink(bc_filename)
