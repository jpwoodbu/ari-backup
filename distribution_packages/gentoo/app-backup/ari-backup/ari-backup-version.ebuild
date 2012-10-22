# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

EAPI=4

DESCRIPTION="Automate VM backups with lvm snapshots."
HOMEPAGE="https://github.com/jpwoodbu/ari-backup"
SRC_URI="https://github.com/jpwoodbu/ari-backup.git"
EGIT_REPO_URI="git://github.com/jpwoodbu/ari-backup.git"

LICENSE=""
SLOT="0"
KEYWORDS="x86"
IUSE=""

DEPEND="app-backup/rdiff-backup dev-python/pyyaml"
RDEPEND="${DEPEND}"

PYTHON_DEPEND="*"

inherit distutils
inherit git-2
inherit python

src_unpack() {
	git-2_src_unpack
}

src_install() {
	distutils_src_install

	insinto /etc/cron.daily
	newins include/cron/ari-backup ari-backup
	fperms 0755 /etc/cron.daily/ari-backup

	dodir /etc/ari-backup
	insinto /etc/ari-backup
	newins include/etc/ari-backup/ari-backup.conf.yaml ari-backup.conf.yaml
	fperms 0660 /etc/ari-backup/ari-backup.conf.yaml

	dodir /etc/ari-backup/jobs.d
}
