#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention App Center
#  univention-app module for upgrading an app
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

from univention.appcenter.app_cache import Apps
from univention.appcenter.actions.install import Install
from univention.appcenter.ucr import ucr_is_true


class Upgrade(Install):

	'''Upgrades an installed application from the Univention App Center.'''
	help = 'Upgrade an app'

	pre_readme = 'readme_update'
	post_readme = 'readme_post_update'

	def __init__(self):
		super(Upgrade, self).__init__()
		# original_app: The App installed when the whole action started
		# old_app: The current App installed when trying to upgrade
		#   - should be the same most of the time. But Docker Apps may upgrade
		#   themselves multiple times during one run and old_app will be set
		#   after each iteration
		self.original_app = self.old_app = None

	def setup_parser(self, parser):
		super(Install, self).setup_parser(parser)
		parser.add_argument('--do-not-install-master-packages-remotely', action='store_false', dest='install_master_packages_remotely', help='Do not install master packages on DC master and DC backup systems')

	def _app_too_old(self, current_app, specified_app):
		if current_app >= specified_app:
			self.fatal('A newer version of %s than the one installed must be present and chosen' % current_app.id)
			return True
		return False

	def main(self, args):
		app = args.app
		self.original_app = self.old_app = Apps().find(app.id)
		if app == self.old_app:
			app = Apps().find_candidate(app) or app
		if self._app_too_old(self.old_app, app):
			return
		args.app = app
		return self.do_it(args)

	def _install_only_master_packages(self, args):
		return False

	def _revert(self, app, args):
		try:
			self.log('Trying to revert to old version. This may lead to problems, but it is better than leaving it the way it is now')
			self._do_it(self.old_app, args)
		except Exception:
			pass

	def _show_license(self, app, args):
		if app.license_agreement != self.old_app.license_agreement:
			return super(Upgrade, self)._show_license(app, args)

	def _call_prescript(self, app, args):
		return super(Upgrade, self)._call_prescript(app, args, old_version=self.old_app.version)

	def _send_information(self, app, status):
		if app > self.original_app:
			super(Upgrade, self)._send_information(app, status)

	def _install_packages(self, packages, percentage_end, update=True):
		super(Upgrade, self)._install_packages(packages, 0, update=update)
		return self._apt_get('dist-upgrade', [], percentage_end, update=False)

	@classmethod
	def iter_upgradable_apps(self):
		for app in Apps().get_all_locally_installed_apps():
			if ucr_is_true(app.ucr_upgrade_key):
				yield app
