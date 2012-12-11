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

"""Implementation of subcmd: submit"""

import os
import time

from gitbuildsys.utils import edit
from gitbuildsys.errors import GbsError
from gitbuildsys.log import LOGGER as log

from gbp.rpm.git import GitRepositoryError, RpmGitRepository



def get_message():
    '''
    get message from editor
    '''
    prompt = '''
# Please enter the message for your tag. Lines starting with '#'
# will be ignored, and an empty message aborts the submission.
#'''
    raw = edit(prompt)
    useful = [i for i in raw.splitlines() if not i.startswith('#') ]
    return os.linesep.join(useful).strip()


def main(args):
    """gbs submit entry point."""

    workdir = args.gitdir

    message = args.msg
    if message is None:
        message = get_message()

    if not message:
        raise GbsError("tag message is required")

    try:
        repo = RpmGitRepository(workdir)
        commit = repo.rev_parse(args.commit)
        current_branch = repo.get_branch()
    except GitRepositoryError, err:
        raise GbsError(str(err))

    try:
        upstream = repo.get_upstream_branch(current_branch)
    except GitRepositoryError:
        upstream = None

    if not args.remote:
        if upstream:
            args.remote = upstream.split('/')[0]
        else:
            log.info("no upstream set for the current branch, using "
                       "'origin' as the remote server")
            args.remote = 'origin'

    target = args.target
    if not target:
        if upstream and upstream.startswith(args.remote):
            target = os.path.basename(upstream)
        else:
            log.warning("Can't find upstream branch for current branch "
                          "%s. Gbs uses the local branch name as the target. "
                          "Please consider to use git-branch --set-upstream "
                          "to set upstream remote branch." % current_branch)
            target = current_branch

    if target == 'master':
        target = 'trunk'

    tagname = 'submit/%s/%s' % (target, time.strftime( \
                                    '%Y%m%d.%H%M%S', time.gmtime()))
    log.info('creating tag: %s' % tagname)
    try:
        repo.create_tag(tagname, msg=message, commit=commit, sign=args.sign,
                        keyid=args.user_key)
    except GitRepositoryError, err:
        raise GbsError('failed to create tag %s: %s ' % (tagname, str(err)))

    log.info("pushing tag to remote '%s'" % args.remote)
    try:
        repo.push_tag(args.remote, tagname)
    except GitRepositoryError, err:
        repo.delete_tag(tagname)
        raise GbsError('failed to push tag %s :%s' % (tagname, str(err)))

    log.info('done.')
