#!/usr/bin/python -tt
# vim: ai ts=4 sts=4 et sw=4
#
# Copyright (c) 2011 Intel, Inc.
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

"""Implementation of subcmd: build
"""

import os
import tempfile
import glob

import msger
from conf import configmgr
import obspkg
import errors
from utils import Workdir

import gbp.rpm
from gbp.scripts.buildpackage_rpm import main as gbp_build
from gbp.git import repository

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

APISERVER   = configmgr.get('build_server', 'remotebuild')
USER        = configmgr.get('user', 'remotebuild')
PASSWDX     = configmgr.get('passwdx', 'remotebuild')
TMPDIR      = configmgr.get('tmpdir')

def do(opts, args):

    workdir = os.getcwd()
    if len(args) > 1:
        msger.error('only one work directory can be specified in args.')
    if len(args) == 1:
        workdir = args[0]
    try:
        repo = repository.GitRepository(workdir)
    except repository.GitRepositoryError:
        msger.error('%s is not a git dir' % workdir)

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
    (fds, oscrcpath) = tempfile.mkstemp(dir=tmpdir, prefix='.oscrc')
    os.close(fds)
    with file(oscrcpath, 'w+') as foscrc:
        foscrc.write(oscrc)

    # TODO: check ./packaging dir at first
    specs = glob.glob('%s/packaging/*.spec' % workdir)
    if not specs:
        msger.error('no spec file found under /packaging sub-directory')

    specfile = specs[0] #TODO:
    if len(specs) > 1:
        msger.warning('multiple specfiles found.')

    # get 'name' and 'version' from spec file
    spec = gbp.rpm.parse_spec(specfile)
    if not spec.name or not spec.version:
        msger.error('can\'t get correct name or version from spec file.')

    if opts.base_obsprj is None:
        # TODO, get current branch of git to determine it
        base_prj = 'Trunk'
    else:
        base_prj = opts.base_obsprj

    if opts.target_obsprj is None:
        target_prj = "home:%s:gbs:%s" % (USER, base_prj)
    else:
        target_prj = opts.target_obsprj

    prj = obspkg.ObsProject(target_prj, apiurl = APISERVER, oscrc = oscrcpath)
    msger.info('checking status of obs project: %s ...' % target_prj)
    try:
        if prj.is_new():
            if opts.target_obsprj and not target_prj.startswith('home:%s:' % USER):
                msger.error('no permission to create project %s, only subpackage '\
                        'of home:%s is allowed ' % (target_prj, USER))
            msger.info('creating %s for package build ...' % target_prj)
            prj.branch_from(base_prj)
    except errors.ObsError, exc:
        msger.error('%s' % exc)

    msger.info('checking out %s/%s to %s ...' % (target_prj, spec.name, tmpdir))
    localpkg = obspkg.ObsPackage(tmpdir, target_prj, spec.name,
                                 APISERVER, oscrcpath)
    oscworkdir = localpkg.get_workdir()
    localpkg.remove_all()

    with Workdir(workdir):
        if gbp_build(["argv[0] placeholder", "--git-export-only",
                      "--git-ignore-new", "--git-builder=osc",
                      "--git-export-dir=%s" % oscworkdir,
                      "--git-packaging-dir=packaging"]):
            msger.error("Failed to get packaging info from git tree")

    localpkg.update_local()

    try:
        msger.info('commit packaging files to build server ...')
        localpkg.commit ('submit packaging files to obs for OBS building')
    except errors.ObsError, e:
        msger.error('commit packages fail: %s, please check the permission '\
                    'of target project:%s' % (e,target_prj))

    os.unlink(oscrcpath)
    msger.info('local changes submitted to build server successfully')
    msger.info('follow the link to monitor the build progress:\n'
               '  %s/package/show?package=%s&project=%s' \
               % (APISERVER.replace('api', 'build'), spec.name, target_prj))
