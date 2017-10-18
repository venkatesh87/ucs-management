#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention App Center
#  univention-app module for starting/stopping an app
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

import os.path

from univention.appcenter.app_cache import Apps
from univention.appcenter.actions import UniventionAppAction, StoreAppAction

ORIGINAL_INIT_SCRIPT = '/usr/share/docker-app-container-init-script'


class Service(UniventionAppAction):

	def setup_parser(self, parser):
		parser.add_argument('app', action=StoreAppAction, help='The ID of the app that shall be controlled')

	@classmethod
	def get_init(cls, app):
		return '/etc/init.d/docker-app-%s' % app.id

	def call_init(self, app, command):
		init = self.get_init(app)
		if not os.path.exists(init):
			self.fatal('%s is not supported' % app.id)
			return False
		return self._call_script(self.get_init(app), command)


class Start(Service):

	'''Starts an application previously installed.'''
	help = 'Start an app'

	def main(self, args):
		return self.call_init(args.app, 'start')


class Stop(Service):

	'''Stops a running application.'''
	help = 'Stop an app'

	def main(self, args):
		return self.call_init(args.app, 'stop')


class Restart(Service):

	'''Restarts an app. Stops and Starts. Does not have to be running'''
	help = 'Restart an app'

	def main(self, args):
		return self.call_init(args.app, 'restart')


class CRestart(Service):

	'''CRestarts an app. Stops and Starts. Has to be running'''
	help = 'CRestart an app'

	def main(self, args):
		return self.call_init(args.app, 'crestart')


class Status(Service):

	'''Ask service about status. Possible answers: running stopped'''
	help = 'Retrieve status of an app'

	@classmethod
	def get_init(cls, app):
		if app.plugin_of:
			app = Apps().find(app.plugin_of)
		return super(Status, cls).get_init(app)

	def main(self, args):
		return self.call_init(args.app, 'status')
