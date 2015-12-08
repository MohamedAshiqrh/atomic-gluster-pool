#!/usr/bin/python
import os
import sys
import paramiko
import getpass
from optparse import OptionParser,Option

pwd=os.getcwd()
pword=None
port="2379"
etcd_server=""
flannel_etcd="flannel-config.json"
etcd_conf="etcd.conf"
fnet_conf="10-flannel-network.conf"
flanneld="flanneld"
docker="docker"
path={}
path[flannel_etcd]="/root/"
path[etcd_conf]="/etc/etcd/"
path[fnet_conf]="/etc/systemd/system/docker.service.d/"
path[flanneld]="/etc/sysconfig/"
path[docker]="/etc/sysconfig/"
fl_etcd=""
fl_opt='FLANNEL_OPTIONS="--iface=eth0 -ip-masq=true"'
doc_opt="--ip-masq=false"
doc_insec_reg="INSECURE_REGISTRY='--insecure-registry docker-registry.usersys.redhat.com'"
tag={}
tag[fl_etcd]="FLANNEL_ETCD"
tag[fl_opt]="FLANNEL_OPTIONS"
tag[doc_opt]="OPTIONS"
tag[doc_insec_reg]="INSECURE_REGISTRY"

class file_handle(object):

    def __init__ (self, host):
        self.sftp = host.open_sftp()

    def if_path(self, path):
        try:
            self.sftp.stat(path)
        except IOError,e:
            if e.errno == errno.ENOENT:
                self.sftp.mkdir(path)
            raise

    def open_pwd(self, name):
        fopen=open(pwd+"/"+name,'r')
        return fopen.read()

    def fcopy (self,fname):
        self.if_path(path[fname])
        ftmp=self.open_pwd(fname)
        s=self.sftp.open(path[fname]+fname,'w')
        s.write(ftmp)

    def fchange_word (self, fname, data):
        self.if_path(path[fname])
        s=self.sftp.open(path[fname]+fname,'r')
        ftmp=s.readlines()
        fline=len(ftmp)
        for i in range(fline):
            ftmp[i]=ftmp[i].replace(data[0],data[1])
        s=self.sftp.open(path[fname]+fname,'w')
        s.writelines(ftmp)

    def fchange_line (self, fname, data):
        self.if_path(path[fname])
        s=self.sftp.open(path[fname]+fname,'r')
        ftmp=s.readlines()
        fline=len(ftmp)
        for i in range(fline):
            if tag[data] in ftmp[i]:
                ftmp[i]=data
        s=self.sftp.open(path[fname]+fname,'w')
        s.writelines(ftmp)

    def fchange_append (self, fname, data):
        self.if_path(path[fname])
        s=self.sftp.open(path[fname]+fname,'r')
        ftmp=s.readlines()
        fline=len(ftmp)
        for i in range(fline):
            if tag[data] in ftmp[i]:
                ltmp=ftmp[i]
                ftmp[i]=ltmp[:-1]+" "+data+ltmp[-1]
        s=self.sftp.open(path[fname]+fname,'w')
        s.writelines(ftmp)

def host_access (node):
    global pword
    if pword == None:
        pword=getpass.getpass("Password for "+node+":")
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(node, username='root', password=pword)
    return ssh

def etcd_server_conf (etcd):
    global fl_etcd
    etcd_ssh=host_access(etcd)
    etcd_sys=etcd_ssh.get_transport().open_session()
    fh = file_handle (etcd_ssh)
    fh.fcopy(flannel_etcd)
    fh.fchange_word(etcd_conf,["localhost","0.0.0.0"])
    etcd_sys.exec_command("service etcd restart")
    etcd_sys.exec_command("curl -L http://localhost:2379/v2/keys/atomic01/network/config -XPUT --data-urlencode value@flannel-config.json")
    etcd_sys.exec_command("curl -L http://localhost:2379/v2/keys/atomic01/network/config| python -m json.tool")
    fh.fcopy(fnet_conf)
    fl_etcd='FLANNEL_ETCD="http://'+etcd_server+':'+port+'"'
    fh.fchange_line(flanneld,fl_etcd)
    fh.fchange_line(flanneld,fl_opt)
    fh.fchange_append(docker,doc_opt)
    etcd_sys.exec_command("sudo systemctl daemon-reload")
    etcd_sys.exec_command("sudo systemctl enable flanneld")
    etcd_sys.exec_command("sudo systemctl enable etcd")
    etcd_sys.exec_command("sudo systemctl reboot")
    print etcd+" configuration complete."

def host_conf (host):
    host_ssh=host_access(host)
    host_sys=host_ssh.get_transport().open_session()
    fh = file_handle (host_ssh)
    host_sys.exec_command("curl -L http://"+etcd_server+":2379/v2/keys/atomic01/network/config")
    fh.fcopy(fnet_conf)
    fl_etcd='FLANNEL_ETCD="http://'+etcd_server+':'+port+'"'
    fh.fchange_line(flanneld,fl_etcd)
    fh.fchange_line(flanneld,fl_opt)
    fh.fchange_append(docker,doc_opt)
    host_sys.exec_command("sudo systemctl enable flanneld ln -s '/usr/lib/systemd/system/flanneld.service''/etc/systemd/system/docker.service.requires/flanneld.service'")
    host_sys.exec_command("curl -L http://"+etcd_server+":2379/v2/keys/atomic01/network/config| python -m json.tool")

class MultipleOption(Option):
    ACTIONS = Option.ACTIONS + ("extend",)
    STORE_ACTIONS = Option.STORE_ACTIONS + ("extend",)
    TYPED_ACTIONS = Option.TYPED_ACTIONS + ("extend",)
    ALWAYS_TYPED_ACTIONS = Option.ALWAYS_TYPED_ACTIONS + ("extend",)

    def take_action(self, action, dest, opt, value, values, parser):
        if action == "extend":
            values.ensure_value(dest, []).append(value.split(","))
        else:
            Option.take_action(self, action, dest, opt, value, values, parser)

def add_options(parser):
    parser.add_option(
        "-e", "--etcd_server",
        action="store",
        dest="etcd",
        help="Configures the host to an Etcd server")
    
    parser.add_option(
        "-i", "--hosts",
        action="extend",
        dest="hosts",
        help="Configures the host to be a node for the etcd server")

    parser.add_option(
        "-p", "--password",
        action="store",
        dest="pword",
        help="password, If all the host has same password")

    return parser

def main():
    global etcd_server
    global pword
    parser = OptionParser(option_class=MultipleOption)
    parser = add_options(parser)
    options, arguments = parser.parse_args()
    print "ETCD SERVER:"+options.etcd
    print "HOSTS:"+str(options.hosts)
    print "PASSWORD"+options.pword
    etcd_server = options.etcd
    hosts = options.hosts
    pword = options.pword
    etcd_server_conf(etcd_server)
    for host in hosts:
        host_conf(host)

if __name__ == '__main__':
    main()
