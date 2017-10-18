# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for prohibited usernames
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

from univention.admin.layout import Tab, Group
import univention.admin.syntax
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization

import univention.debug

translation = univention.admin.localization.translation('univention.admin.handlers.settings')
_ = translation.translate

module = 'settings/prohibited_username'
operations = ['add', 'edit', 'remove', 'search', 'move']
superordinate = 'settings/cn'

childs = 0
short_description = _('Settings: Prohibited user names')
long_description = _('Univention Prohibited user names')
options = {
}
property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description=_('Name'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=True,
		identifies=True,
	),
	'usernames': univention.admin.property(
		short_description=_('Prohibited user name'),
		long_description=_('Prohibited user name'),
		syntax=univention.admin.syntax.string,
		multivalue=True,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False,
	),
}

layout = [
	Tab(_('General'), _('Prohibited user names'), layout=[
		Group(_('General prohibited user names settings'), layout=[
			'name',
			'usernames',
		]),
	]),
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('usernames', 'prohibitedUsername', None, None)


class object(univention.admin.handlers.simpleLdap):
	module = module

	def _ldap_addlist(self):
		return [('objectClass', ['top', 'univentionProhibitedUsernames'])]


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionProhibitedUsernames')
	])

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = []
	try:
		for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
			res.append(object(co, lo, None, dn, attributes=attrs))
	except:
		pass
	return res


def identify(dn, attr, canonical=0):
	return 'univentionProhibitedUsernames' in attr.get('objectClass', [])
