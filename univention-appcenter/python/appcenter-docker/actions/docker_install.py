#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention App Center
#  univention-app module for installing an app
#  (docker version)
#
# Copyright 2015-2017 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.
#

from argparse import SUPPRESS

from univention.appcenter.actions.configure import StoreConfigAction
from univention.appcenter.actions.install import Install
from univention.appcenter.actions.docker_base import DockerActionMixin
from univention.appcenter.actions import Abort, get_action
from univention.appcenter.ucr import ucr_save
from univention.appcenter.utils import _


class Install(Install, DockerActionMixin):

	def setup_parser(self, parser):
		super(Install, self).setup_parser(parser)
		parser.add_argument('--set', nargs='+', action=StoreConfigAction, metavar='KEY=VALUE', dest='set_vars', help='Sets the configuration variable. Example: --set some/variable=value some/other/variable="value 2"')
		parser.add_argument('--do-not-revert', action='store_false', dest='revert', help=SUPPRESS)  # debugging

	def _install_app(self, app, args):
		if not app.docker:
			return super(Install, self)._install_app(app, args)
		else:
			if app.plugin_of:
				return self._install_app_in_existing_container(app, args)
			hostdn, password = self._register_host(app, args)
			self.percentage = 30
			self._start_docker_image(app, hostdn, password, args)
			self.percentage = 50
			self._setup_docker_image(app, args)
			return True

	def _do_it(self, app, args):
		ret = super(Install, self)._do_it(app, args)
		if app.docker:
			ucr_save({'appcenter/prudence/docker/%s' % app.id: None})
		return ret

	def _revert(self, app, args):
		if not args.revert:
			return
		try:
			password = self._get_password(args, ask=False)
			remove = get_action('remove')
			remove.call(app=app, noninteractive=args.noninteractive, username=args.username, password=password, send_info=False, skip_checks=[], backup=False)
		except Exception:
			pass

	def _install_app_in_existing_container(self, app, args):
		self._setup_docker_image(app, args)
		ucr_save({app.ucr_container_key: self._get_docker(app).container})
		return True

	def _setup_docker_image(self, app, args):
		self._execute_container_script(app, 'restore_data_before_setup', _credentials=False)
		if app.docker_script_setup:
			process = self._execute_container_script(app, 'setup', args)
			if not process or process.returncode != 0:
				raise Abort(_('Setup script failed!'))
		self._execute_container_script(app, 'restore_data_after_setup', _credentials=False)
