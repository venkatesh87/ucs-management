# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for network objects
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

import ipaddr
import string
import ldap
from ldap.filter import filter_format

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.uexceptions
import univention.admin.localization

import univention.debug

translation = univention.admin.localization.translation('univention.admin.handlers.networks')
_ = translation.translate

module = 'networks/network'
operations = ['add', 'edit', 'remove', 'search']
childs = 0
short_description = _('Networks: Network')
long_description = ''

property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		required=True,
		may_change=False,
		identifies=True
	),
	'network': univention.admin.property(
		short_description=_('Networks'),
		long_description='',
		syntax=univention.admin.syntax.ipAddress,
		multivalue=False,
		include_in_default_search=True,
		required=True,
		may_change=False,
		identifies=False
	),
	'netmask': univention.admin.property(
		short_description=_('Netmask'),
		long_description='',
		syntax=univention.admin.syntax.netmask,
		multivalue=False,
		include_in_default_search=True,
		required=True,
		may_change=False,
		identifies=False
	),
	'nextIp': univention.admin.property(
		short_description=_('Next IP address'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'ipRange': univention.admin.property(
		short_description=_('IP address range'),
		long_description='',
		syntax=univention.admin.syntax.IP_AddressRange,
		multivalue=True,
		dontsearch=True,
		required=False,
		may_change=True,
		identifies=False
	),
	'dnsEntryZoneForward': univention.admin.property(
		short_description=_('DNS forward lookup zone'),
		long_description='',
		syntax=univention.admin.syntax.DNS_ForwardZone,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'dnsEntryZoneReverse': univention.admin.property(
		short_description=_('DNS reverse lookup zone'),
		long_description='',
		syntax=univention.admin.syntax.DNS_ReverseZone,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'dhcpEntryZone': univention.admin.property(
		short_description=_('DHCP service'),
		long_description='',
		syntax=univention.admin.syntax.dhcpService,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
}

layout = [
	Tab(_('General'), _('Basic settings'), layout=[
		Group(_('General network settings'), layout=[
			'name',
			['network', 'netmask'],
			'ipRange',
		]),
		Group(_('DNS preferences'), layout=[
			'dnsEntryZoneForward',
			'dnsEntryZoneReverse',
		]),
		Group(_('DHCP preferences'), layout=[
			'dhcpEntryZone',
		]),
	]),
]


def rangeMap(value):
	return map(lambda x: ' '.join(x), value)


def rangeUnmap(value):
	return map(lambda x: x.split(' '), value)


mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('network', 'univentionNetwork', None, univention.admin.mapping.ListToString)
mapping.register('netmask', 'univentionNetmask', None, univention.admin.mapping.ListToString)
mapping.register('nextIp', 'univentionNextIp', None, univention.admin.mapping.ListToString)
mapping.register('dnsEntryZoneForward', 'univentionDnsForwardZone', univention.admin.mapping.IgnoreNone, univention.admin.mapping.ListToString)
mapping.register('dnsEntryZoneReverse', 'univentionDnsReverseZone', univention.admin.mapping.IgnoreNone, univention.admin.mapping.ListToString)
mapping.register('dhcpEntryZone', 'univentionDhcpEntry', univention.admin.mapping.IgnoreNone, univention.admin.mapping.ListToString)
mapping.register('ipRange', 'univentionIpRange', rangeMap, rangeUnmap)


class object(univention.admin.handlers.simpleLdap):
	module = module

	def stepIp(self):
		network = ipaddr.IPNetwork(self['network'] + '/' + self['netmask'])
		if self['nextIp']:
			# nextIP is already set:
			#	- check range for actual ip
			#	- inc ip
			#	- check for range
			currentIp = ipaddr.IPAddress(self['nextIp'])
			newIp = ipaddr.IPAddress(self['nextIp']) + 1
			for ipRange in self['ipRange']:
				if not ipRange:  # ignore bad default value self['ipRange'] = ['']
					continue
				firstIP = ipaddr.IPAddress(ipRange[0])
				lastIP = ipaddr.IPAddress(ipRange[1])
				if firstIP <= currentIp <= lastIP:
					if firstIP <= newIp <= lastIP:
						self['nextIp'] = str(newIp)
					else:
						position = (self['ipRange'].index(ipRange) + 1) % len(self['ipRange'])  # find "next" ipRange
						self['nextIp'] = self['ipRange'][position][0]  # select first IP of that range
						if ipaddr.IPAddress(self['nextIp']) == network.network:  # do not give out all hostbits zero
							self['nextIp'] = str(ipaddr.IPAddress(self['nextIp']) + 1)
					break
			else:  # currentIp is not in any ipRange
				if self['ipRange'] and self['ipRange'][0]:  # ignore bad default value self['ipRange'] = ['']
					self['nextIp'] = self['ipRange'][0][0]
					if ipaddr.IPAddress(self['nextIp']) == network.network:  # do not give out all hostbits zero
						self['nextIp'] = str(ipaddr.IPAddress(self['nextIp']) + 1)
				else:  # did not find nextIp in ipRanges because ipRanges are empty
					if newIp in network:
						self['nextIp'] = str(newIp)
					else:
						self['nextIp'] = str(network.network + 1)  # first useable host address in network
		elif self['ipRange']:
			# nextIP is not set
			# 	- use first ip range entry
			self['nextIp'] = self['ipRange'][0][0]
			if ipaddr.IPAddress(self['nextIp']) == network.network:  # do not give out all hostbits zero
				self['nextIp'] = str(ipaddr.IPAddress(self['nextIp']) + 1)
		elif self['network']:
			# nextIP is not set, no IPrange, then we use the first ip of the network
			self['nextIp'] = str(network.network + 1)  # first useable host address in network

	def refreshNextIp(self):
		start_ip = self['nextIp']
		while self.lo.search(scope='domain', attr=['aRecord'], filter=filter_format('(&(aRecord=%s))', [self['nextIp']])) or self['nextIp'].split('.')[-1] in ['0', '1', '254']:
			self.stepIp()
			if self['nextIp'] == start_ip:
				raise univention.admin.uexceptions.nextFreeIp
		self.modify()

	def _ldap_post_remove(self):
		import univention.admin.handlers.computers.computer
		filter_ = univention.admin.filter.expression('univentionNetworkLink', self.dn)
		for computer in univention.admin.handlers.computers.computer.lookup(self.co, self.lo, filter_s=filter_):
			try:
				self.lo.modify(computer.dn, [('univentionNetworkLink', self.dn, '')])
			except (univention.admin.uexceptions.base, ldap.LDAPError):
				import traceback
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'Failed to remove network %s from %s: %s' % (self.dn, computer.dn, traceback.format_exc()))

	def _ldap_addlist(self):
		if not self['nextIp']:
			self.stepIp()

		return [
			('objectClass', ['top', 'univentionNetworkClass']),
		]

	def _ldap_modlist(self):

		ml = univention.admin.handlers.simpleLdap._ldap_modlist(self)

		next_ip_changed = False

		if self.hasChanged('ipRange'):
			network = ipaddr.IPNetwork(self['network'] + '/' + self['netmask'])
			currentIp = ipaddr.IPAddress(self['nextIp'])
			if self['ipRange']:
				self.sort_ipranges()
				self['nextIp'] = self['ipRange'][0][0]
			else:
				self['nextIp'] = str(network.network + 1)
			if self['nextIp'] != self.oldattr.get('univentionNextIp', ''):
				next_ip_changed = True

			ipRange = []
			for i in self['ipRange']:
				firstIP = ipaddr.IPAddress(i[0])
				lastIP = ipaddr.IPAddress(i[1])
				for j in self['ipRange']:
					if i != j:
						otherFirstIP = ipaddr.IPAddress(j[0])
						otherLastIP = ipaddr.IPAddress(j[1])
						if firstIP < otherFirstIP < lastIP or \
							firstIP < otherLastIP < lastIP or \
							otherFirstIP < firstIP < otherLastIP or \
							otherFirstIP < lastIP < otherLastIP:
							raise univention.admin.uexceptions.rangesOverlapping('%s-%s; %s-%s' % (i[0], i[1], j[0], j[1]))
				if firstIP not in network or lastIP not in network:
					raise univention.admin.uexceptions.rangeNotInNetwork('%s-%s' % (firstIP, lastIP, ))
				if firstIP == network.network or lastIP == network.network:
					raise univention.admin.uexceptions.rangeInNetworkAddress('%s-%s' % (firstIP, lastIP, ))
				if firstIP == network.broadcast or lastIP == network.broadcast:
					raise univention.admin.uexceptions.rangeInBroadcastAddress('%s-%s' % (firstIP, lastIP, ))
				ipRange.append(string.join(i, ' '))
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'old Range: %s' % self.oldinfo.get('ipRange'))
			ml.append(('univentionIpRange', self.oldattr.get('univentionIpRange', ['']), ipRange))

		if next_ip_changed:
			for el in ml:  # mapping may have set nextIp already, we want our value
				if el[0] == 'univentionNextIp':
					ml.remove(el)
			ml.append(('univentionNextIp', self.oldattr.get('univentionNextIp', ''), self['nextIp']))

		return ml

	def sort_ipranges(self):
		# make sure that the ipRanges are ordered by their start address (smallest first)
		for i in range(1, len(self['ipRange'])):
			if ipaddr.IPAddress(self['ipRange'][i][0]) < ipaddr.IPAddress(self['ipRange'][i - 1][0]):
				self['ipRange'].insert(i - 1, self['ipRange'].pop(i))
		for i in range(1, len(self['ipRange'])):
			if ipaddr.IPAddress(self['ipRange'][i][0]) < ipaddr.IPAddress(self['ipRange'][i - 1][0]):
				self.sort_ipranges()


def rewrite(filter, mapping):
	univention.admin.mapping.mapRewrite(filter, mapping)


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionNetworkClass'),
	])

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, rewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = []
	for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
		res.append(object(co, lo, None, dn, attributes=attrs))
	return res


def identify(dn, attr, canonical=0):

	return 'univentionNetworkClass' in attr.get('objectClass', [])
