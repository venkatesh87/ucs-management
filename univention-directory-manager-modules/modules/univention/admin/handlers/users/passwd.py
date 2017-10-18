# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for password part of the user
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

import univention.admin
from univention.admin.layout import Tab
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization
import univention.admin.uexceptions
import univention.admin.uldap
import univention.admin.handlers.users.user

import univention.debug

translation = univention.admin.localization.translation('univention.admin.handlers.users')
_ = translation.translate

module = 'users/passwd'
operations = ['edit']
uid_umlauts = 0

childs = 0
short_description = _('User: Password')
long_description = ''
options = {}
property_descriptions = {
	'username': univention.admin.property(
		short_description=_('User name'),
		long_description='',
		syntax=univention.admin.syntax.uid,
		multivalue=False,
		include_in_default_search=True,
		required=True,
		may_change=False,
		identifies=True
	),
	'password': univention.admin.property(
		short_description=_('Password'),
		long_description='',
		syntax=univention.admin.syntax.userPasswd,
		multivalue=False,
		options=['posix', 'samba', 'kerberos', 'mail'],
		required=True,
		may_change=True,
		identifies=False,
		dontsearch=True
	),
}

layout = [
	Tab(_('Change password'), _('Change password'), [
		'password'])
]

object = univention.admin.handlers.users.user.object
