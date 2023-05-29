# -*- mode: ruby -*-
# vi: set ft=ruby :

$py38 = <<SCRIPT
set -o errexit

apt-get install -y python3.8
apt-get install -y python3.8-dev python3.8-venv
# update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1
apt-get install -y python3-pip
update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1
SCRIPT

$bootstrap_basic = <<SCRIPT
set -o errexit

function get_ip() {
    DEV=${1:-'eth0'}
    ip -4 addr show $DEV 2>/dev/null | grep -oP "(?<=inet ).*(?=/)" | head -1
}

apt-get update
apt-get -y upgrade

timedatectl set-timezone America/New_York

apt-get install -y git wget vim emacs-nox

# ip route
apt-get install -y net-tools

# tmate -- https://github.com/GameServerManagers/LinuxGSM/issues/817
#apt-get install -y telnet tmate
apt-get install -y locales
localedef -f UTF-8 -i en_US en_US.UTF-8

passwd -l root

SSHD_CNF='/etc/ssh/sshd_config'
cp -v ${SSHD_CNF}{,.orig}
sed -i "s/^PermitRootLogin .*$/PermitRootLogin prohibit-password/" ${SSHD_CNF}
sed -i "s/#StrictModes .*$/StrictModes yes/" ${SSHD_CNF}
sed -i "s/#PasswordAuthentication .*$/PasswordAuthentication no/" ${SSHD_CNF}
sed -i "s/#PermitEmptyPasswords .*$/PermitEmptyPasswords no/" ${SSHD_CNF}
systemctl restart sshd

apt-get install -y ufw fail2ban
ufw allow OpenSSH
yes | ufw enable
SCRIPT

$bootstrap_basic_always = <<SCRIPT
# TODO(flaviof): this needs to be more generic
# default routes
route add default gw 192.168.30.254
route add -net 192.168.2.0/24 gw 192.168.30.254
route add -net 192.168.10.0/24 gw 192.168.30.254
SCRIPT

Vagrant.configure(2) do |config|

    vm_memory = ENV['VM_MEMORY'] || '1024'
    vm_cpus = ENV['VM_CPUS'] || '4'

    config.ssh.forward_agent = true
    config.vm.hostname = "adavm"

    # TODO(flaviof): this needs to be more generic
    config.vm.network "public_network", ip: "192.168.30.253",
                     :dev => "bridge0",
                     :mode => "bridge",
                     :type => "bridge"

    config.vm.box = "generic/ubuntu1804"
    config.vm.synced_folder "#{ENV['PWD']}", "/vagrant", sshfs_opts_append: "-o nonempty", disabled: false, type: "sshfs"
    #config.vm.synced_folder "#{ENV['PWD']}", "/vagrant", disabled: false, type: "rsync"

    # https://github.com/vagrant-libvirt/vagrant-libvirt#domain-specific-options
    config.vm.provider 'libvirt' do |lb|
        lb.autostart = true
        lb.random_hostname = true
        lb.nested = true
        lb.memory = vm_memory
        lb.cpus = vm_cpus
        lb.suspend_mode = 'managedsave'
    end
    config.vm.provider "virtualbox" do |vb|
       vb.memory = vm_memory
       vb.cpus = vm_cpus
       vb.customize ["modifyvm", :id, "--nested-hw-virt", "on"]
       vb.customize ["modifyvm", :id, "--nictype1", "virtio"]
       vb.customize ["modifyvm", :id, "--nictype2", "virtio"]
       vb.customize ['modifyvm', :id, "--nicpromisc2", "allow-all"]
       vb.customize [
           "guestproperty", "set", :id,
           "/VirtualBox/GuestAdd/VBoxService/--timesync-set-threshold", 10000
          ]
    end

    config.vm.provision :shell do |shell|
        shell.privileged = true
        shell.path = 'provision/baseProvision.sh'
    end

    config.vm.provision "bootstrap_basic", type: "shell",
        inline: $bootstrap_basic

    if File.exist? "#{ENV['HOME']}/.secrets" then
        config.vm.provision "shell", inline: <<-SCRIPT
          printf "%s\n" "#{File.read("#{ENV['HOME']}/.secrets")}" >> /vagrant/provision/secrets.txt
        SCRIPT
    end
    config.vm.provision :shell do |shell|
        shell.privileged = false
        shell.path = 'provision/provision_secrets.sh'
    end
    config.vm.provision :shell do |shell|
        shell.path = 'provision/provision_mqtt_broker.sh'
    end
    # config.vm.provision :shell do |shell|
    #     shell.privileged = false
    #     shell.path = 'provision/provision_ring_mqtt.sh'
    # end

    config.vm.provision "py38", type: "shell",
        inline: $py38

    config.vm.provision :shell do |shell|
        shell.privileged = false
        shell.path = 'provision/provision_evbays.sh'
    end

    config.vm.provision "bootstrap_basic_always", type: "shell",
        run: "always",
        inline: $bootstrap_basic_always

    config.vm.provision :shell do |shell|
        shell.privileged = false
        shell.path = 'provision/provision_ada_io.sh'
    end

end
