// Test-copy only. Guest-memory helper for the Strikeforce autotester.
// FindBase uses the same two signature words as tp2.cs (tested 27-Nov 2026).
// Unique type name so Add-Type does not clash with TP2/GM already loaded in a session.
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;

public static class SFAT_VM {
    [DllImport("kernel32")] static extern IntPtr OpenProcess(int a, bool b, int p);
    [DllImport("kernel32")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
    [DllImport("kernel32")] static extern bool WriteProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
    [DllImport("kernel32")] static extern IntPtr VirtualQueryEx(IntPtr h, IntPtr a, out MBI m, IntPtr l);
    [StructLayout(LayoutKind.Sequential)]
    public struct MBI {
        public IntPtr Base, Alloc;
        public uint AP, pad0;
        public IntPtr Size;
        public uint State, Prot, Type, pad1;
    }
    public static IntPtr H;
    public static long VB;

    public static void Open(int pid) { H = OpenProcess(0x1F0FFF, false, pid); }
    public static uint R32(long ga) {
        byte[] b = new byte[4]; IntPtr r;
        ReadProcessMemory(H, (IntPtr)(VB + ga), b, (IntPtr)4, out r);
        return (uint)(b[0] << 24 | b[1] << 16 | b[2] << 8 | b[3]);
    }
    public static void W32(long ga, uint v) {
        byte[] b = { (byte)(v >> 24), (byte)(v >> 16), (byte)(v >> 8), (byte)v }; IntPtr r;
        WriteProcessMemory(H, (IntPtr)(VB + ga), b, (IntPtr)4, out r);
    }
    public static float RF(long ga) {
        uint u = R32(ga);
        return BitConverter.ToSingle(BitConverter.GetBytes(u), 0);
    }
    public static void WF(long ga, float f) {
        byte[] t = BitConverter.GetBytes(f);
        byte[] b = { t[3], t[2], t[1], t[0] }; IntPtr r;
        WriteProcessMemory(H, (IntPtr)(VB + ga), b, (IntPtr)4, out r);
    }
    public static byte R8(long ga) {
        byte[] b = new byte[1]; IntPtr r;
        ReadProcessMemory(H, (IntPtr)(VB + ga), b, (IntPtr)1, out r);
        return b[0];
    }
    public static void W8(long ga, byte v) {
        byte[] b = { v }; IntPtr r;
        WriteProcessMemory(H, (IntPtr)(VB + ga), b, (IntPtr)1, out r);
    }
    // Guest image base: R32(0x8487B0)==0xB4 and R32(0xDB8710)==0x11103500.
    public static string FindBase() {
        var seen = new HashSet<long>(); long a = 0; MBI m; var outp = "";
        while (VirtualQueryEx(H, (IntPtr)a, out m, (IntPtr)Marshal.SizeOf(typeof(MBI))) != IntPtr.Zero) {
            long al = (long)m.Alloc;
            if (m.State == 0x1000 && al != 0 && seen.Add(al)) {
                VB = al;
                try {
                    if (R32(0x8487B0) == 0xB4 && R32(0xDB8710) == 0x11103500)
                        outp += al.ToString("X") + " ";
                } catch { }
            }
            a = (long)m.Base + (long)m.Size;
            if (a <= 0) break;
        }
        return outp;
    }
    public static byte[] Snap(long ga, int len) {
        byte[] b = new byte[len]; IntPtr r;
        for (int o = 0; o < len; o += 0x10000) {
            int n = Math.Min(0x10000, len - o);
            byte[] c = new byte[n];
            if (ReadProcessMemory(H, (IntPtr)(VB + ga + o), c, (IntPtr)n, out r))
                Buffer.BlockCopy(c, 0, b, o, n);
        }
        return b;
    }
    public static float F(byte[] b, int o) {
        byte[] t = { b[o + 3], b[o + 2], b[o + 1], b[o] };
        return BitConverter.ToSingle(t, 0);
    }
    public static uint U(byte[] b, int o) {
        return (uint)(b[o] << 24 | b[o + 1] << 16 | b[o + 2] << 8 | b[o + 3]);
    }
}
