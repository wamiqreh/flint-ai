using System;
using System.IO;
using System.Threading.Tasks;
using Npgsql;

namespace Orchestrator.Infrastructure.Migrations{    public static class MigrationRunner    {        public static async Task RunMigrationsAsync(string connectionString, string migrationsFolder)        {            if (string.IsNullOrEmpty(connectionString)) return;            if (!Directory.Exists(migrationsFolder)) return;            var files = Directory.GetFiles(migrationsFolder, "*.sql");            Array.Sort(files);            await using var conn = new NpgsqlConnection(connectionString);            await conn.OpenAsync();            foreach (var file in files)            {                var sql = await File.ReadAllTextAsync(file);                if (string.IsNullOrWhiteSpace(sql)) continue;                await using var cmd = new NpgsqlCommand(sql, conn);                await cmd.ExecuteNonQueryAsync();            }        }    }}


