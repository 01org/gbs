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

"""Implementation of subcmd: submit
"""

import os
import time

from gbp.rpm.git import GitRepositoryError, RpmGitRepository
import msger
import errors

def do(opts, args):

    workdir = os.getcwd()
    if len(args) > 1:
        msger.error('only one work directory can be specified in args.')
    if len(args) == 1:
        workdir = os.path.abspath(args[0])

    if opts.msg is None:
        raise errors.Usage('message for tag must be specified with -m option')

    try:
        repo = RpmGitRepository(workdir)
        commit = repo.rev_parse(opts.commit)
        if opts.target:
            target_branch = opts.target
        else:
            target_branch = repo.get_branch()
    except GitRepositoryError, err:
        msger.error(str(err))

    if not opts.target:
        try:
            upstream = repo.get_upstream([target_branch])
            upstream_branch = upstream[target_branch]
            if upstream_branch and upstream_branch.startswith(opts.remote):
                target_branch = os.path.basename(upstream_branch)
            else:
                msger.warning('can\'t find upstream branch for current branch '\
                              '%s. Gbs will try to find it by name. Please '\
                              'consider to use git-branch --set-upstream to '\
                              'set upstream remote branch.' % target_branch)
        except GitRepositoryError:
            pass

    try:
        if target_branch == 'master':
            target_branch = 'trunk'
        tagname = 'submit/%s/%s' % (target_branch, time.strftime( \
                                    '%Y%m%d.%H%M%S', time.gmtime()))
        msger.info('creating tag: %s' % tagname)
        repo.create_tag(tagname, msg=opts.msg, commit=commit, sign=opts.sign,
                                                 keyid=opts.user_key)
    except GitRepositoryError, err:
        msger.error('failed to create tag %s: %s ' % (tagname, str(err)))

    try:
        msger.info('pushing tag to remote server')
        repo.push_tag(opts.remote, tagname)
    except GitRepositoryError, err:
        repo.delete_tag(tagname)
        msger.error('failed to push tag %s :%s' % (tagname, str(err)))

    msger.info('done.')
