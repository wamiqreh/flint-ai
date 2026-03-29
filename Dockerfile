FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

COPY . .
RUN dotnet restore ./src/Orchestrator.Api/Orchestrator.Api.csproj
RUN dotnet publish ./src/Orchestrator.Api/Orchestrator.Api.csproj -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /app/publish .

ENV ASPNETCORE_URLS=http://+:5156
EXPOSE 5156

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 CMD curl -fsS http://localhost:5156/health || exit 1

ENTRYPOINT ["dotnet", "Orchestrator.Api.dll"]
