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

import os

# internal modules
import runner
import errors
import msger

class Git:
    def __init__(self, path):
        try:
            os.stat(os.path.join(path,'.git'))
        except:
            raise errors.GitInvalid(path)

        self.path = os.path.abspath(path)
        os.chdir(self.path)

    def _check_path(self):
        if os.getcwd() != self.path:
            raise GitRepositoryError

    def _git_command(self, command, args=[]):
        """exec a git command and return the output"""

        cmd = ['git', command] + args
        msger.debug(cmd)
        return runner.runtool(cmd)

    def status(self):
        return self._git_command('status')

    def get_files(self):
        """return the files list"""
        ret, out = self._git_command('ls-files')
        print self._git_command('ls-files')
        if ret:
            raise GitRepositoryError, "Error listing files %d" % ret
        if out:
            return [ file for file in out.split('\n') if file ]
        else:
            return []

    def get_branches(self):
        """
        return the branches list, current working
        branch is the first element
        """
        self._check_path()
        branches = []
        for line in self._git_command('branch', [ '--no-color' ])[1].split('\n'):
            if line.startswith('*'):
                current_branch=line.split(' ', 1)[1].strip()
            else:
                branches.append(line.strip())

        return (current_branch, branches)

    def is_clean(self):
        """does the repository contain any uncommitted modifications"""
        self._check_path()
        clean_msg = 'nothing to commit'
        out = self._git_command('status')[1]
        ret = False
        for line in out:
            if line.startswith('#'):
                continue
            if line.startswith(clean_msg):
                    ret = True
            break
        return (ret, "".join(out))

    def has_branch(self, branch, remote=False):
        """
        check if the repository has branch 'branch'
        @param remote: only liste remote branches
        """

        options = [ '--no-color' ]
        if remote:
            options += [ '-r' ]

        for line in self._git_command('branch', options)[1]:
            if line.split(' ', 1)[1].strip() == branch:
                return True
        return False
