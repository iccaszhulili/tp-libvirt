import logging
import os
import shutil

from virttest import virsh
from virttest import utils_libvirtd
from virttest import utils_selinux
from virttest.utils_test import libvirt
from virttest.libvirt_xml import vm_xml


def run(test, params, env):
    def check_ga_state(start_ga):
        # The session is just to make sure the guest
        # is fully boot up
        session = vm.wait_for_login()
        cur_xml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        channels = cur_xml.get_agent_channels()
        for channel in channels:
            state = channel.find('./target').get('state')
        logging.debug("The guest agent state is %s", state)
        agent_status = state == "connected"
        if start_ga != agent_status:
            test.fail("guest agent device should be in %s "
                      "state" % state)
        session.close()

    def check_ga_function():
        error_msg = []
        if status_error:
            error_msg.append("QEMU guest agent is not connected")
        if hotunplug_ga:
            error_msg.append("QEMU guest agent is not configured")
        result = virsh.domtime(vm_name, ignore_status=True, debug=True)
        libvirt.check_result(result, expected_fails=error_msg,
                             any_error=status_error)

    def get_ga_xml():
        cur_xml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        channels = cur_xml.get_devices('channel')
        for channel in channels:
            target = channel['xmltreefile'].find('./target')
            if target is not None:
                name = target.get('name')
                if name and name.startswith("org.qemu.guest_agent"):
                    ga_xml = channel.xml
                    break
        return ga_xml

    vm_name = params.get("main_vm")
    status_error = ("yes" == params.get("status_error", "no"))
    start_ga = ("yes" == params.get("start_ga", "yes"))
    prepare_channel = ("yes" == params.get("prepare_channel", "yes"))
    src_path = params.get("src_path")
    tgt_name = params.get("tgt_name", "org.qemu.guest_agent.0")
    restart_libvirtd = ("yes" == params.get("restart_libvirtd"))
    suspend_resume_guest = ("yes" == params.get("suspend_resume_guest"))
    hotunplug_ga = ("yes" == params.get("hotunplug_ga"))
    label = params.get("con_label")

    if src_path:
        socket_file_dir = os.path.dirname(src_path)
        if not os.path.exists(socket_file_dir):
            os.mkdir(socket_file_dir)
        shutil.chown(socket_file_dir, "qemu", "qemu")
        utils_selinux.set_context_of_file(filename=socket_file_dir,
                                          context=label)

    vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm_name)
    backup_xml = vmxml.copy()
    vmxml.remove_agent_channels()
    vmxml.sync()

    try:
        vm = env.get_vm(vm_name)
        if prepare_channel:
            vm.prepare_guest_agent(start=start_ga, channel=True,
                                   source_path=src_path)

        if restart_libvirtd:
            utils_libvirtd.libvirtd_restart()

        if suspend_resume_guest:
            virsh.suspend(vm_name, ignore_status=True, debug=True)
            virsh.resume(vm_name, ignore_status=True, debug=True)

        if hotunplug_ga:
            ga_xml = get_ga_xml()
            result = virsh.detach_device(vm_name, ga_xml)
            if result.exit_status:
                test.fail("hotunplug guest agent device failed, %s"
                          % result)
            vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
            if vmxml.get_agent_channels():
                test.fail("hotunplug guest agent device failed as "
                          "guest agent xml still exists")
        else:
            check_ga_state(start_ga)

        check_ga_function()
    finally:
        vm.destroy()
        backup_xml.sync()
