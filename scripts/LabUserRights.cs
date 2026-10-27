using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;

public static class MrngLabUserRights
{
    [StructLayout(LayoutKind.Sequential)]
    private struct Attributes
    {
        public int Length;
        public IntPtr RootDirectory, ObjectName;
        public uint Flags;
        public IntPtr SecurityDescriptor, SecurityQualityOfService;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct UnicodeString
    {
        public ushort Length, MaximumLength;
        public IntPtr Buffer;
    }
    [DllImport("advapi32.dll")]
    private static extern uint LsaOpenPolicy(IntPtr system, ref Attributes attributes, uint access, out IntPtr handle);
    [DllImport("advapi32.dll")]
    private static extern uint LsaAddAccountRights(IntPtr handle, byte[] sid, UnicodeString[] rights, uint count);
    [DllImport("advapi32.dll")]
    private static extern uint LsaRemoveAccountRights(IntPtr handle, byte[] sid,
        [MarshalAs(UnmanagedType.U1)] bool allRights, UnicodeString[] rights, uint count);
    [DllImport("advapi32.dll")]
    private static extern uint LsaClose(IntPtr handle);
    [DllImport("advapi32.dll")]
    private static extern uint LsaNtStatusToWinError(uint status);

    public static void SetBatchLogon(string accountSid, bool grant)
    {
        var sid = new SecurityIdentifier(accountSid);
        byte[] binarySid = new byte[sid.BinaryLength];
        sid.GetBinaryForm(binarySid, 0);
        var attributes = new Attributes { Length = Marshal.SizeOf(typeof(Attributes)) };
        IntPtr handle;
        Check(LsaOpenPolicy(IntPtr.Zero, ref attributes, 0x810, out handle));
        const string name = "SeBatchLogonRight";
        IntPtr buffer = Marshal.StringToHGlobalUni(name);
        try
        {
            var rights = new[] { new UnicodeString {
                Buffer = buffer, Length = (ushort)(name.Length * 2), MaximumLength = (ushort)(name.Length * 2 + 2)
            } };
            Check(grant ? LsaAddAccountRights(handle, binarySid, rights, 1) :
                          LsaRemoveAccountRights(handle, binarySid, false, rights, 1));
        }
        finally { Marshal.FreeHGlobal(buffer); LsaClose(handle); }
    }

    private static void Check(uint status)
    {
        if (status != 0) throw new Win32Exception((int)LsaNtStatusToWinError(status));
    }
}
