#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention Nagios
#  univention admin nagios module
#
# Copyright 2004-2017 Univention GmbH
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

import re
from ldap.filter import filter_format

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.syntax
import univention.admin.localization
from univention.admin import configRegistry

translation = univention.admin.localization.translation('univention.admin.handlers.nagios')
_ = translation.translate

module = 'nagios/service'

childs = 0
short_description = _('Nagios service')
long_description = ''
operations = ['search', 'edit', 'add', 'remove']

ldap_search_period = univention.admin.syntax.LDAP_Search(
	filter='(objectClass=univentionNagiosTimeperiodClass)',
	attribute=['nagios/timeperiod: name'],
	value='nagios/timeperiod: name')


property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description=_('Service name'),
		syntax=univention.admin.syntax.string_numbers_letters_dots,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=False,
		identifies=True
	),
	'description': univention.admin.property(
		short_description=_('Description'),
		long_description=_('Service description'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'checkCommand': univention.admin.property(
		short_description=_('Plugin command'),
		long_description=_('Command name of Nagios plugin'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'checkArgs': univention.admin.property(
		short_description=_('Plugin command arguments'),
		long_description=_('Arguments of used Nagios plugin'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'useNRPE': univention.admin.property(
		short_description=_('Use NRPE'),
		long_description=_('Use NRPE to check remote services'),
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'checkPeriod': univention.admin.property(
		short_description=_('Check period'),
		long_description=_('Check services within check period'),
		syntax=ldap_search_period,
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'maxCheckAttempts': univention.admin.property(
		short_description=_('Maximum number of check attempts'),
		long_description=_('Maximum number of check attempts with non-OK-result until contact will be notified'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		default='10',
		identifies=False,
		size='One',
	),
	'normalCheckInterval': univention.admin.property(
		short_description=_('Check interval'),
		long_description=_('Interval between checks'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		default='10',
		identifies=False,
		size='One',
	),
	'retryCheckInterval': univention.admin.property(
		short_description=_('Retry check interval'),
		long_description=_('Interval between re-checks if service is in non-OK-state'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		default='1',
		identifies=False,
		size='One',
	),
	'notificationInterval': univention.admin.property(
		short_description=_('Notification interval'),
		long_description=_('Interval between notifications'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		default='180',
		identifies=False,
		size='One',
	),
	'notificationPeriod': univention.admin.property(
		short_description=_('Notification period'),
		long_description=_('Send notifications during this period'),
		syntax=ldap_search_period,
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'notificationOptionWarning': univention.admin.property(
		short_description=_('Notify if service state changes to WARNING'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		options=[],
		default='1',
		may_change=True,
		identifies=False
	),
	'notificationOptionCritical': univention.admin.property(
		short_description=_('Notify if service state changes to CRITICAL'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		options=[],
		default='1',
		may_change=True,
		identifies=False
	),
	'notificationOptionUnreachable': univention.admin.property(
		short_description=_('Notify if service state changes to UNREACHABLE'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		options=[],
		default='1',
		may_change=True,
		identifies=False
	),
	'notificationOptionRecovered': univention.admin.property(
		short_description=_('Notify if service state changes to RECOVERED'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		options=[],
		default='1',
		may_change=True,
		identifies=False
	),
	'assignedHosts': univention.admin.property(
		short_description=_('Assigned hosts'),
		long_description=_('Check services on these hosts'),
		syntax=univention.admin.syntax.nagiosHostsEnabledDn,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	)
}


layout = [
	Tab(_('General'), _('Basic settings'), layout=[
		Group(_('General Nagios service settings'), layout=[
			["name", "description"],
			["checkCommand", "checkArgs"],
			"useNRPE"
		]),
	]),
	Tab(_('Interval'), _('Check settings'), advanced=True, layout=[
		["normalCheckInterval", "retryCheckInterval"],
		["maxCheckAttempts", "checkPeriod"]
	]),
	Tab(_('Notification'), _('Notification settings'), advanced=True, layout=[
		["notificationInterval", "notificationPeriod"],
		"notificationOptionWarning",
		"notificationOptionCritical",
		"notificationOptionUnreachable",
		"notificationOptionRecovered"
	]),
	Tab(_('Hosts'), _('Assigned hosts'), layout=[
		Group(_('Assigned hosts'), layout=[
			"assignedHosts"
		]),
	]),
]


mapping = univention.admin.mapping.mapping()

mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('description', 'description', None, univention.admin.mapping.ListToString)
mapping.register('checkCommand', 'univentionNagiosCheckCommand', None, univention.admin.mapping.ListToString)
mapping.register('checkArgs', 'univentionNagiosCheckArgs', None, univention.admin.mapping.ListToString)
mapping.register('useNRPE', 'univentionNagiosUseNRPE', None, univention.admin.mapping.ListToString)

mapping.register('normalCheckInterval', 'univentionNagiosNormalCheckInterval', None, univention.admin.mapping.ListToString)
mapping.register('retryCheckInterval', 'univentionNagiosRetryCheckInterval', None, univention.admin.mapping.ListToString)
mapping.register('maxCheckAttempts', 'univentionNagiosMaxCheckAttempts', None, univention.admin.mapping.ListToString)
mapping.register('checkPeriod', 'univentionNagiosCheckPeriod', None, univention.admin.mapping.ListToString)

mapping.register('notificationInterval', 'univentionNagiosNotificationInterval', None, univention.admin.mapping.ListToString)
mapping.register('notificationPeriod', 'univentionNagiosNotificationPeriod', None, univention.admin.mapping.ListToString)


class object(univention.admin.handlers.simpleLdap):
	module = module

	def open(self):
		univention.admin.handlers.simpleLdap.open(self)
		if self.exists():
			if self.oldattr.get('univentionNagiosNotificationOptions', []):
				options = self.oldattr.get('univentionNagiosNotificationOptions', [])[0].split(',')
				if 'w' in options:
					self['notificationOptionWarning'] = '1'
				else:
					self['notificationOptionWarning'] = '0'

				if 'c' in options:
					self['notificationOptionCritical'] = '1'
				else:
					self['notificationOptionCritical'] = '0'

				if 'u' in options:
					self['notificationOptionUnreachable'] = '1'
				else:
					self['notificationOptionUnreachable'] = '0'

				if 'r' in options:
					self['notificationOptionRecovered'] = '1'
				else:
					self['notificationOptionRecovered'] = '0'

		_re = re.compile('^([^.]+)\.(.+?)$')

		# convert host FQDN to host DN
		hostlist = []
		hosts = self.oldattr.get('univentionNagiosHostname', [])
		for host in hosts:
			# split into relDomainName and zoneName
			if host and _re.match(host) is not None:
				(relDomainName, zoneName) = _re.match(host).groups()
				# find correct dNSZone entry
				res = self.lo.search(filter=filter_format('(&(objectClass=dNSZone)(zoneName=%s)(relativeDomainName=%s)(aRecord=*))', (zoneName, relDomainName)))
				if not res:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'service.py: open: couldn''t find dNSZone of %s' % host)
				else:
					# found dNSZone
					filter = '(&(objectClass=univentionHost)'
					for aRecord in res[0][1]['aRecord']:
						filter += filter_format('(aRecord=%s)', [aRecord])
					filter += filter_format('(cn=%s))', [relDomainName])

					# find dn of host that is related to given aRecords
					res = self.lo.search(filter=filter)
					if res:
						hostlist.append(res[0][0])

		self['assignedHosts'] = hostlist

		self.save()

	def _ldap_post_create(self):
		pass

	def _ldap_pre_modify(self):
		pass

	def _ldap_post_modify(self):
		pass

	def _ldap_pre_remove(self):
		pass

	def _ldap_post_remove(self):
		pass

	def _update_policies(self):
		pass

	def _ldap_addlist(self):
		return [('objectClass', ['top', 'univentionNagiosServiceClass'])]

	def _ldap_modlist(self):
		ml = univention.admin.handlers.simpleLdap._ldap_modlist(self)

		options = []
		if self['notificationOptionWarning'] in ['1']:
			options.append('w')
		if self['notificationOptionCritical'] in ['1']:
			options.append('c')
		if self['notificationOptionUnreachable'] in ['1']:
			options.append('u')
		if self['notificationOptionRecovered'] in ['1']:
			options.append('r')

		# univentionNagiosNotificationOptions is required in LDAP schema
		if len(options) == 0:
			options.append('n')

		newoptions = ','.join(options)
		ml.append(('univentionNagiosNotificationOptions', self.oldattr.get('univentionNagiosNotificationOptions', []), newoptions))

		# save assigned hosts
		if self.hasChanged('assignedHosts'):
			hostlist = []
			for hostdn in self.info.get('assignedHosts', []):
				domain = self.lo.getAttr(hostdn, 'associatedDomain')
				cn = self.lo.getAttr(hostdn, 'cn')
				if not domain:
					domain = [configRegistry.get("domainname")]
				fqdn = "%s.%s" % (cn[0], domain[0])
				hostlist.append(fqdn)

			ml.insert(0, ('univentionNagiosHostname', self.oldattr.get('univentionNagiosHostname', []), hostlist))

		return ml


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):
	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionNagiosServiceClass'),
	])

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = []
	for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
		res.append(object(co, lo, None, dn, attributes=attrs))
	return res


def identify(dn, attr, canonical=0):
	return 'univentionNagiosServiceClass' in attr.get('objectClass', [])
