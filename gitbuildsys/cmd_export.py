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

"""Implementation of subcmd: export
"""

import os
import shutil
import errno

from gitbuildsys import msger, runner, utils, errors
from gitbuildsys.conf import configmgr

from gbp.scripts.buildpackage_rpm import main as gbp_build
from gbp.rpm.git import GitRepositoryError, RpmGitRepository
import gbp.rpm as rpm
from gbp.errors import GbpError


def mkdir_p(path):
    """
    Create directory as in mkdir -p
    """
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST:
            pass
        else:
            raise

def is_native_pkg(repo):
    """
    Determine if the package is "native"
    """
    return not repo.has_branch("upstream")

def create_gbp_export_args(repo, commit, export_dir, spec, force_native=False):
    """
    Construct the cmdline argument list for git-buildpackage export
    """
    args = ["argv[0] placeholder", "--git-export-only",
            "--git-ignore-new", "--git-builder=osc",
            "--git-upstream-branch=upstream",
            "--git-export-dir=%s" % export_dir,
            "--git-packaging-dir=packaging",
            "--git-spec-file=%s" % spec,
            "--git-export=%s" % commit]
    if force_native or is_native_pkg(repo):
        args.extend(["--git-no-patch-export",
                     "--git-upstream-tree=%s" % commit])
    else:
        args.extend(["--git-patch-export",
                     "--git-patch-export-compress=100k",
                     "--git-force-create",])
        if repo.has_branch("pristine-tar"):
            args.extend(["--git-pristine-tar"])

    return args

def export_sources(repo, commit, export_dir, spec):
    """
    Export packaging files using git-buildpackage
    """
    gbp_args = create_gbp_export_args(repo, commit, export_dir, spec)
    try:
        ret = gbp_build(gbp_args)
        if ret and not is_native_pkg(repo):
            # Try falling back to old logic of one monolithic tarball
            msger.warning("Generating upstream tarball and/or generating "\
                          "patches failed. GBS tried this as you have "\
                          "upstream branch in you git tree. This is a new "\
                          "mode introduced in GBS v0.10. "\
                          "Consider fixing the problem by either:\n"\
                          "  1. Update your upstream branch and/or fix the "\
                          "spec file\n"\
                          "  2. Remove or rename the upstream branch")
            msger.info("Falling back to the old method of generating one "\
                       "monolithic source archive")
            gbp_args = create_gbp_export_args(repo, commit, export_dir,
                                              spec, force_native=True)
            ret = gbp_build(gbp_args)
        if ret:
            msger.error("Failed to get export packaging files from git tree")
    except GitRepositoryError, excobj:
        msger.error("Repository error: %s" % excobj)


def do(opts, args):
    """
    The main plugin call
    """
    workdir = os.getcwd()

    if len(args) > 1:
        msger.error('only one work directory can be specified in args.')
    if len(args) == 1:
        workdir = os.path.abspath(args[0])

    if opts.commit and opts.include_all:
        raise errors.Usage('--commit can\'t be specified together with '\
                           '--include-all')

    try:
        repo = RpmGitRepository(workdir)
    except GitRepositoryError, err:
        msger.error(str(err))

    utils.git_status_checker(repo, opts)
    workdir = repo.path

    if not os.path.exists("%s/packaging" % workdir):
        msger.error('No packaging directory, so there is nothing to export.')

    # Only guess spec filename here, parse later when we have the correct
    # spec file at hand
    specfile = utils.guess_spec(workdir, opts.spec)

    outdir = "%s/packaging" % workdir
    if opts.outdir:
        outdir = opts.outdir
    mkdir_p(outdir)
    outdir = os.path.abspath(outdir)
    tmpdir     = configmgr.get('tmpdir', 'general')
    tempd = utils.Temp(prefix=os.path.join(tmpdir, '.gbs_export_'), \
                       directory=True)
    export_dir = tempd.path

    with utils.Workdir(workdir):
        if opts.commit:
            commit = opts.commit
        elif opts.include_all:
            commit = 'WC.UNTRACKED'
        else:
            commit = 'HEAD'
        relative_spec = specfile.replace('%s/' % workdir, '')
        export_sources(repo, commit, export_dir, relative_spec)

    try:
        spec = rpm.parse_spec(os.path.join(export_dir,
                                           os.path.basename(specfile)))
    except GbpError, err:
        msger.error('%s' % err)

    if not spec.name or not spec.version:
        msger.error('can\'t get correct name or version from spec file.')
    else:
        outdir = "%s/%s-%s-%s" % (outdir, spec.name, spec.upstreamversion,
                                  spec.release)
        shutil.rmtree(outdir, ignore_errors=True)
        shutil.move(export_dir, outdir)

    if opts.source_rpm:
        cmd = ['rpmbuild',
               '--short-circuit', '-bs',
               '--define "_topdir %s"' % outdir,
               '--define "_builddir %_topdir"',
               '--define "_buildrootdir %_topdir"',
               '--define "_rpmdir %_topdir"',
               '--define "_sourcedir %_topdir"',
               '--define "_specdir %_topdir"',
               '--define "_srcrpmdir %_topdir"',
               specfile
              ]
        runner.quiet(' '.join(cmd))
        msger.info('source rpm generated to:\n     %s/%s.src.rpm' % \
                   (outdir, os.path.basename(outdir)))

    msger.info('package files have been exported to:\n     %s' % outdir)
