#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention App Center
#  univention-app module for uninstalling an app
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

from univention.appcenter.actions.install_base import InstallRemoveUpgrade
from univention.appcenter.ucr import ucr_save


class Remove(InstallRemoveUpgrade):

	'''Removes an application from the Univention App Center.'''
	help = 'Uninstall an app'

	prescript_ext = 'prerm'
	pre_readme = 'readme_uninstall'
	post_readme = 'readme_post_uninstall'

	def main(self, args):
		return self.do_it(args)

	def _show_license(self, app, args):
		pass

	def _do_it(self, app, args):
		self._remove_app(app, args)
		self.percentage = 45
		self._unregister_app(app, args)
		self.percentage = 50
		self._unregister_attributes(app, args)
		self.percentage = 60
		if self._unregister_component(app):
			self._apt_get_update()
		self.percentage = 70
		self._unregister_files(app)
		self.percentage = 80
		self._call_unjoin_script(app, args)
		if not app.docker:
			ucr_save({'appcenter/prudence/docker/%s' % app.id: 'yes'})

	def _remove_app(self, app, args):
		self._apt_get('remove', app.get_packages(additional=False), 45, update=False)
