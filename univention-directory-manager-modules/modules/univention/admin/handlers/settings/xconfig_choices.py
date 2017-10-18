# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for xconfig choices
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

import ldap

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.password
import univention.admin.localization

translation = univention.admin.localization.translation('univention.admin.handlers.settings')
_ = translation.translate


def plusBase(object, arg):
	return [arg + ',' + object.position.getDomain()]


module = 'settings/xconfig_choices'
superordinate = 'settings/cn'
childs = 0
width = "100"
operations = ['search', 'edit']
short_description = _('Preferences: X Configuration Choices')
long_description = ''
options = {
}
property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=False,
		identifies=True,
	),
	'resolution': univention.admin.property(
		short_description=_('Resolution'),
		long_description='',
		syntax=univention.admin.syntax.XResolution,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'colorDepth': univention.admin.property(
		short_description=_('Color Depth'),
		long_description='',
		syntax=univention.admin.syntax.integer,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'mouseProtocol': univention.admin.property(
		short_description=_('Mouse Protocol'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'mouseDevice': univention.admin.property(
		short_description=_('Mouse Device'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'keyboardLayout': univention.admin.property(
		short_description=_('Keyboard Layout'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'keyboardVariant': univention.admin.property(
		short_description=_('Keyboard Variant'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'hSync': univention.admin.property(
		short_description=_('Horizontal Sync'),
		long_description='',
		syntax=univention.admin.syntax.XSync,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'vRefresh': univention.admin.property(
		short_description=_('Vertical Refresh'),
		long_description='',
		syntax=univention.admin.syntax.XSync,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'xModule': univention.admin.property(
		short_description=_('X Module'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'displaySize': univention.admin.property(
		short_description=_('Display Size (mm)'),
		long_description='',
		syntax=univention.admin.syntax.XResolution,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
}

layout = [
	Tab(_('General'), _('X Configuration Choices'), layout=[
		Group(_('General X configuration choices settings'), layout=[
			'name',
			['resolution', 'colorDepth'],
			['mouseProtocol', 'mouseDevice'],
			['keyboardLayout', 'keyboardVariant'],
			['hSync', 'vRefresh'],
			'displaySize',
		]),
	]),
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('xModule', 'univentionXModuleChoices')
mapping.register('resolution', 'univentionXResolutionChoices')
mapping.register('colorDepth', 'univentionXColorDepthChoices')
mapping.register('mouseProtocol', 'univentionXMouseProtocolChoices')
mapping.register('mouseDevice', 'univentionXMouseDeviceChoices')
mapping.register('keyboardLayout', 'univentionXKeyboardLayoutChoices')
mapping.register('keyboardVariant', 'univentionXKeyboardVariantChoices')
mapping.register('hSync', 'univentionXHSyncChoices')
mapping.register('vRefresh', 'univentionXVRefreshChoices')
mapping.register('displaySize', 'univentionXDisplaySizeChoices')


class object(univention.admin.handlers.simpleLdap):
	module = module

	def _ldap_dn(self):
		dn = ldap.dn.str2dn(super(object, self)._ldap_dn())
		return '%s,cn=univention,%s' % (ldap.dn.dn2str(dn[0]), self.position.getDomain())

	def _ldap_addlist(self):
		return [('objectClass', ['top', 'univentionXConfigurationChoices'])]


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', 'univentionXConfigurationChoices')
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

	return 'univentionXConfigurationChoices' in attr.get('objectClass', [])
