#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention App Center
#  univention-app module for installing an app
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
from univention.appcenter.actions import Abort, get_action
from univention.appcenter.actions.install_base import InstallRemoveUpgrade
from univention.appcenter.udm import search_objects
from univention.appcenter.ucr import ucr_get, ucr_is_true, ucr_save


class ControlScriptException(Exception):
	pass


class Install(InstallRemoveUpgrade):

	'''Installs an application from the Univention App Center.'''
	help = 'Install an app'

	prescript_ext = 'preinst'
	pre_readme = 'readme_install'
	post_readme = 'readme_post_install'

	def setup_parser(self, parser):
		super(Install, self).setup_parser(parser)
		parser.add_argument('--only-master-packages', action='store_true', help='Install only master packages')
		parser.add_argument('--do-not-install-master-packages-remotely', action='store_false', dest='install_master_packages_remotely', help='Do not install master packages on DC master and DC backup systems')

	def main(self, args):
		app = args.app
		if app._docker_prudence_is_true():
			apps = [_app for _app in Apps().get_all_apps_with_id(app.id) if not _app.docker]
			if apps:
				app = sorted(apps)[-1]
				self.warn('Using %s instead of %s because docker is to be ignored' % (app, args.app))
			else:
				raise Abort('Cannot use %s as docker is to be ignored, yet, only non-docker versions could be found' % args.app)
		args.app = app
		return self.do_it(args)

	def _install_only_master_packages(self, args):
		return args.only_master_packages

	def _do_it(self, app, args):
		if self._install_only_master_packages(args):
			self._install_master_packages(app, unregister_if_uninstalled=True)
		else:
			self._register_files(app)
			self.percentage = 5
			self._register_app(app, args)
			self.percentage = 10
			self._register_database(app)
			self.percentage = 15
			self._register_attributes(app, args)
			self.percentage = 25
			if self._install_app(app, args):
				self.percentage = 80
				self._call_join_script(app, args)
				ucr_save({'appcenter/prudence/docker/%s' % app.id: 'yes'})
			else:
				raise Abort('Failed to install the App')

	def _install_packages(self, packages, percentage_end, update=True):
		return self._apt_get('install', packages, percentage_end, update=update)

	def _install_master_packages(self, app, percentage_end=100, unregister_if_uninstalled=False):
		old_app = Apps().find(app.id)
		was_installed = old_app.is_installed()
		self._register_component(app)
		ret = self._install_packages(app.default_packages_master, percentage_end)
		if was_installed:
			if old_app != app:
				self.log('Re-registering component for %s' % old_app)
				self._register_component(old_app)
				self._apt_get_update()
		elif unregister_if_uninstalled:
			self.log('Unregistering component for %s' % app)
			self._unregister_component(app)
			self._apt_get_update()
		return ret

	def _install_only_master_packages_remotely(self, app, host, is_master, args):
		if args.install_master_packages_remotely:
			self.log('Installing some packages of %s on %s' % (app.id, host))
		else:
			self.warn('Not installing packages on %s. Please make sure that these packages are installed by calling "univention-app install "%s=%s" --only-master-packages" on the host' % (host, app.id, app.version))
			return
		username = 'root@%s' % host
		try:
			if args.noninteractive:
				raise Abort()
			password = self._get_password_for(username)
			with self._get_password_file(password=password) as password_file:
				if not password_file:
					raise Abort()
				# TODO: fallback if univention-app is not installed
				process = self._subprocess(['/usr/sbin/univention-ssh', password_file, username, 'univention-app', 'install', '%s=%s' % (app.id, app.version), '--only-master-packages', '--noninteractive', '--do-not-send-info'])
				if process.returncode != 0:
					self.warn('Installing master packages for %s on %s failed!' % (app.id, host))
		except Abort:
			if is_master:
				self.fatal('This is the DC master. Cannot continue!')
				raise
			else:
				self.warn('This is a DC backup. Continuing anyway, please rerun univention-app install %s --only-master-packages there later!' % (app.id))

	def _find_hosts_for_master_packages(self, args):
		lo, pos = self._get_ldap_connection(args, allow_machine_connection=True)
		hosts = []
		for host in search_objects('computers/domaincontroller_master', lo, pos):
			hosts.append((host.info.get('fqdn'), True))
		for host in search_objects('computers/domaincontroller_backup', lo, pos):
			hosts.append((host.info.get('fqdn'), False))
		try:
			local_fqdn = '%s.%s' % (ucr_get('hostname'), ucr_get('domainname'))
			local_is_master = ucr_get('server/role') == 'domaincontroller_master'
			hosts.remove((local_fqdn, local_is_master))
		except ValueError:
			# not in list
			pass
		return hosts

	def _install_app(self, app, args):
		self._register_component(app)
		install_master = False
		if app.default_packages_master:
			if ucr_get('server/role') == 'domaincontroller_master':
				self._install_master_packages(app, 30)
				install_master = True
			for host, is_master in self._find_hosts_for_master_packages(args):
				self._install_only_master_packages_remotely(app, host, is_master, args)
			if ucr_get('server/role') == 'domaincontroller_backup':
				self._install_master_packages(app, 30)
				install_master = True
		return self._install_packages(app.get_packages(), 80, update=not install_master).returncode == 0

	def _revert(self, app, args):
		try:
			password = self._get_password(args, ask=False)
			remove = get_action('remove')
			remove.call(app=app, noninteractive=args.noninteractive, username=args.username, password=password, send_info=False, skip_checks=[], backup=False)
		except Exception:
			pass
