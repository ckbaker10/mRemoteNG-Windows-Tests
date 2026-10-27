using System.Text.Json;
using mRemoteNG.Security;
using mRemoteNG.Security.Policy;

try
{
    var policy = MachineSecurityPolicy.Current;
    using var key = "Synthetic-Lab-Master-Key-123!".ConvertToSecureString();
    string encrypted = ProtectedSettingsValue.Encrypt("synthetic-probe-secret", key, policy, "lab.probe");
    Console.WriteLine(JsonSerializer.Serialize(new
    {
        policy.RequireMasterPassword,
        policy.MinimumMasterPasswordLength,
        policy.AllowPersistentUnlock,
        policy.RequireFullEncryption,
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
    Console.WriteLine(JsonSerializer.Serialize(new { PolicyLoadFailed = true, ErrorType = exception.GetType().Name }));
    return 2;
}
