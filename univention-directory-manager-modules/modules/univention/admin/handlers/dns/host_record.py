# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for the dns host records
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

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.handlers.dns.forward_zone
import univention.admin.localization

translation = univention.admin.localization.translation('univention.admin.handlers.dns')
_ = translation.translate

module = 'dns/host_record'
operations = ['add', 'edit', 'remove', 'search']
columns = ['a']
superordinate = 'dns/forward_zone'
childs = 0
short_description = 'DNS: Host Record'
long_description = _('Resolve the symbolic name to IP addresses.')

property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Hostname'),
		long_description=_('The name of the host relative to the domain.'),
		syntax=univention.admin.syntax.dnsName,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=True,
		identifies=True
	),
	'zonettl': univention.admin.property(
		short_description=_('Time to live'),
		long_description=_('The time this entry may be cached.'),
		syntax=univention.admin.syntax.UNIX_TimeInterval,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False,
		default=(('3', 'hours'), [])
	),
	'a': univention.admin.property(
		short_description=_('IP addresses'),
		long_description=_('One or more IP addresses, to which the name is resolved to.'),
		syntax=univention.admin.syntax.ipAddress,
		multivalue=True,
		options=[],
		required=False,
		may_change=True
	),
	'mx': univention.admin.property(
		short_description=_('Mail exchanger host'),
		long_description=_('The FQDNs of the hosts responsible for receiving mail for this DNS name.'),
		syntax=univention.admin.syntax.dnsMX,
		multivalue=True,
		options=[],
		required=False,
		may_change=True
	),
	'txt': univention.admin.property(
		short_description=_('Text Record'),
		long_description=_('One or more arbitrary text strings.'),
		syntax=univention.admin.syntax.string,
		multivalue=True,
		options=[],
		required=False,
		may_change=True
	)
}

layout = [
	Tab(_('General'), _('Basic values'), layout=[
		Group(_('General host record settings'), layout=[
			'name',
			'a',
			'zonettl'
		]),
	]),
	Tab(_('Mail'), _('Mail exchangers for this host'), advanced=True, layout=[
		'mx'
	]),
	Tab(_('Text'), _('Optional text'), advanced=True, layout=[
		'txt',
	])
]


def unmapMX(old):
	_d = univention.debug.function('admin.handlers.dns.host_record.unmapMX old=%s' % str(old))
	new = []
	for i in old:
		new.append(i.split(' '))
	return new


def mapMX(old):
	_d = univention.debug.function('admin.handlers.dns.host_record.mapMX old=%s' % str(old))
	new = []
	for i in old:
		new.append(string.join(i, ' '))
	return new


mapping = univention.admin.mapping.mapping()
mapping.register('name', 'relativeDomainName', None, univention.admin.mapping.ListToString)
mapping.register('mx', 'mXRecord', mapMX, unmapMX)
mapping.register('txt', 'tXTRecord')
mapping.register('zonettl', 'dNSTTL', univention.admin.mapping.mapUNIX_TimeInterval, univention.admin.mapping.unmapUNIX_TimeInterval)


class object(univention.admin.handlers.simpleLdap):
	module = module

	def _updateZone(self):
		if self.update_zone:
			self.superordinate.open()
			self.superordinate.modify()

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes=[], update_zone=True):
		self.update_zone = update_zone
		univention.admin.handlers.simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes=attributes)

		if dn:  # TODO: document why or remove
			self.open()

	def open(self):
		univention.admin.handlers.simpleLdap.open(self)
		self.oldinfo['a'] = []
		self.info['a'] = []
		if 'aRecord' in self.oldattr:
			self.oldinfo['a'].extend(self.oldattr['aRecord'])
			self.info['a'].extend(self.oldattr['aRecord'])
		if 'aAAARecord' in self.oldattr:
			self.oldinfo['a'].extend(map(lambda x: ipaddr.IPv6Address(x).exploded, self.oldattr['aAAARecord']))
			self.info['a'].extend(map(lambda x: ipaddr.IPv6Address(x).exploded, self.oldattr['aAAARecord']))

	def _ldap_addlist(self):
		return [
			('objectClass', ['top', 'dNSZone']),
			(self.superordinate.mapping.mapName('zone'), self.superordinate.mapping.mapValue('zone', self.superordinate['zone'])),
		]

	def _ldap_modlist(self):  # IPv6
		ml = univention.admin.handlers.simpleLdap._ldap_modlist(self)
		oldAddresses = self.oldinfo.get('a')
		newAddresses = self.info.get('a')
		oldARecord = []
		newARecord = []
		oldAaaaRecord = []
		newAaaaRecord = []
		if oldAddresses != newAddresses:
			if oldAddresses:
				for address in oldAddresses:
					if ':' in address:  # IPv6
						oldAaaaRecord.append(address)
					else:
						oldARecord.append(address)
			if newAddresses:
				for address in newAddresses:
					if ':' in address:  # IPv6
						newAaaaRecord.append(ipaddr.IPv6Address(address).exploded)
					else:
						newARecord.append(address)

			# explode all IPv6 addresses and remove duplicates
			newAaaaRecord = list(set(map(lambda x: ipaddr.IPv6Address(x).exploded, newAaaaRecord)))

			ml.append(('aRecord', oldARecord, newARecord, ))
			ml.append(('aAAARecord', oldAaaaRecord, newAaaaRecord, ))
		return ml

	def _ldap_post_create(self):
		self._updateZone()

	def _ldap_post_modify(self):
		if self.hasChanged(self.descriptions.keys()):
			self._updateZone()

	def _ldap_post_remove(self):
		self._updateZone()


def lookup(co, lo, filter_s, base='', superordinate=None, scope="sub", unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'dNSZone'),
		univention.admin.filter.conjunction('!', [univention.admin.filter.expression('relativeDomainName', '@')]),
		univention.admin.filter.conjunction('!', [univention.admin.filter.expression('zoneName', '*.in-addr.arpa')]),
		univention.admin.filter.conjunction('!', [univention.admin.filter.expression('zoneName', '*.ip6.arpa')]),
		univention.admin.filter.conjunction('!', [univention.admin.filter.expression('cNAMERecord', '*')]),
		univention.admin.filter.conjunction('!', [univention.admin.filter.expression('sRVRecord', '*')]),
		univention.admin.filter.conjunction('|', [
			univention.admin.filter.expression('aRecord', '*'),
			univention.admin.filter.expression('aAAARecord', '*'),
			univention.admin.filter.expression('mXRecord', '*'),
		]),
	])

	if superordinate:
		filter.expressions.append(univention.admin.filter.expression('zoneName', superordinate.mapping.mapValue('zone', superordinate['zone'])))

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = []
	for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
		res.append((object(co, lo, None, dn=dn, superordinate=superordinate, attributes=attrs)))
	return res


def identify(dn, attr, canonical=0):
	univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'ALIAS(host_record) identify DN=%s' % dn)
	return 'dNSZone' in attr.get('objectClass', []) and '@' not in attr.get('relativeDomainName', []) and \
		not attr['zoneName'][0].endswith('.arpa') and not attr.get('cNAMERecord', []) and \
		not attr.get('sRVRecord', []) and (attr.get('aRecord', []) or attr.get('aAAARecord', []) or attr.get('mXRecord', []))
