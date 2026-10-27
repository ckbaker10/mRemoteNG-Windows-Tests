using System.Text.Json;
using mRemoteNG.Security;
using mRemoteNG.Security.Policy;
using mRemoteNG.Security.KeyManagement;
using System.Security.Principal;

string stage = "policy";
try
{
    var policy = MachineSecurityPolicy.Current;
    stage = "settings-encryption";
    using var key = "Synthetic-Lab-Master-Key-123!".ConvertToSecureString();
    string encrypted = ProtectedSettingsValue.Encrypt("synthetic-probe-secret", key, policy, "lab.probe");
    stage = "persistent-unlock-policy";
    bool persistentUnlockBlocked = CheckPersistentUnlock(policy, key);
    stage = "result";
    Console.WriteLine(JsonSerializer.Serialize(new
    {
        policy.RequireMasterPassword,
        policy.MinimumMasterPasswordLength,
        policy.AllowPersistentUnlock,
        policy.RequireFullEncryption,
        policy.AllowPasswordExport,
        policy.AllowPlaintextExport,
        EncryptionEngine = policy.EncryptionEngine?.ToString(),
        BlockCipherMode = policy.BlockCipherMode?.ToString(),
        policy.MinimumKdfIterations,
        IsAdministrator = new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator),
        PersistentUnlockBlocked = persistentUnlockBlocked,
        DefaultPasswordRejected = MasterPasswordValidator.GetError("mR3m", policy) != null,
        PersonalPasswordAccepted = MasterPasswordValidator.GetError("Synthetic-Lab-Master-Key-123!", policy) == null,
        InvalidComplexityRejected = new[]
        {
            "synthetic-lab-master-key-123!", "SYNTHETIC-LAB-MASTER-KEY-123!",
            "Synthetic-Lab-Master-Key!", "SyntheticLabMasterKey123", "Aa1!"
        }.All(password => MasterPasswordValidator.GetError(password, policy) != null),
        SettingsRoundTrip = ProtectedSettingsValue.Decrypt(encrypted, key, policy, purpose: "lab.probe") == "synthetic-probe-secret",
        SettingsPlaintextAbsent = !encrypted.Contains("synthetic-probe-secret", StringComparison.Ordinal)
    }));
    return 0;
}
catch (Exception exception)
{
    // Type only: exception messages can include local values or file locations.
    Console.WriteLine(JsonSerializer.Serialize(new { PolicyLoadFailed = stage == "policy", ErrorStage = stage, ErrorType = exception.GetType().Name }));
    return 2;
}

static bool CheckPersistentUnlock(SecurityPolicy policy, System.Security.SecureString key)
{
    if (policy.AllowPersistentUnlock) return false;
    string path = Path.Combine(Path.GetTempPath(), "mrng-dpapi-probe-" + Guid.NewGuid().ToString("N"));
    try
    {
        // A prohibited provider must never read, decrypt or delete even an
        // invalid old cache. Network/S4U logons cannot create user DPAPI keys.
        File.WriteAllBytes(path, new byte[] { 0x4d, 0x52, 0x4e, 0x47, 0x00, 0xff });
        byte[] original = File.ReadAllBytes(path);
        var blocked = new DpapiMasterKeyProvider(path, policy);
        bool storeRejected = false;
        try { blocked.StoreKey(key); }
        catch (InvalidOperationException) { storeRejected = true; }
        using var recovered = blocked.GetKeyAsync().GetAwaiter().GetResult();
        return storeRejected && !blocked.IsAvailable && recovered == null &&
               original.SequenceEqual(File.ReadAllBytes(path));
    }
    finally { if (File.Exists(path)) File.Delete(path); }
}
