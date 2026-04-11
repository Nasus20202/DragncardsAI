# Seed script: creates a dev user and installs the Marvel Champions plugin.
# Run with: mix run /app/priv/seed_plugin.exs
#
# Expects plugin files to be mounted at /plugin/:
#   /plugin/json/*.json  - game definition files
#   /plugin/tsv/*.tsv    - card database files

alias DragnCards.{Repo, Plugins, Plugins.Plugin}
alias DragnCards.Users.User
alias DragnCardsUtil.{Merger, TsvProcess}

# --- 1. Ensure dev user exists ---
user =
  case Repo.get_by(User, alias: "dev_user") do
    nil ->
      IO.puts("Creating dev_user...")
      changeset =
        User.changeset(%User{}, %{
          alias: "dev_user",
          email: "dev_user@example.com",
          password: "password",
          password_confirmation: "password",
          supporter_level: 1,
          language: "English",
          plugin_settings: %{}
        })

      {:ok, user} = Repo.insert(changeset)

      # Confirm email so user can log in
      user
      |> Ecto.Changeset.change(%{email_confirmed_at: DateTime.utc_now() |> DateTime.truncate(:second)})
      |> Repo.update!()

    user ->
      IO.puts("dev_user already exists (id: #{user.id})")
      user
  end

# --- 2. Build game_def from JSON files ---
json_dir = "/plugin/json"
json_files =
  Path.wildcard("#{json_dir}/*.json")
  |> Enum.sort()

if json_files == [] do
  IO.puts("ERROR: No JSON files found in #{json_dir}")
  System.halt(1)
end

IO.puts("Merging #{length(json_files)} JSON files...")
# NOTE: We cannot use Merger.merge_json_files/1 because its remove_comments/1
# strips "SP//dr" (a Marvel character name) by treating "//" as a comment marker.
# Instead, we read + decode JSON directly and deep-merge the results.
game_def =
  json_files
  |> Enum.map(fn f -> f |> File.read!() |> Jason.decode!() end)
  |> Merger.deep_merge()

# --- 3. Build card_db from TSV files ---
tsv_dir = "/plugin/tsv"
tsv_files =
  Path.wildcard("#{tsv_dir}/*.tsv")
  |> Enum.sort()

card_db =
  if tsv_files == [] do
    IO.puts("No TSV files found in #{tsv_dir}, using empty card_db")
    %{}
  else
    IO.puts("Processing #{length(tsv_files)} TSV files...")
    Enum.reduce(tsv_files, %{}, fn filename, acc ->
      rows =
        File.stream!(filename)
        |> Stream.map(&String.split(&1, "\t"))
        |> Enum.to_list()

      temp_db = TsvProcess.process_rows(game_def, rows)
      Merger.deep_merge([acc, temp_db])
    end)
  end

# --- 4. Create or update the plugin ---
plugin_name = "Marvel Champions"

case Repo.get_by(Plugin, name: plugin_name) do
  nil ->
    IO.puts("Creating plugin '#{plugin_name}'...")
    {:ok, plugin} =
      Plugins.create_plugin(%{
        "name" => plugin_name,
        "version" => 1,
        "game_def" => game_def,
        "card_db" => card_db,
        "num_favorites" => 0,
        "public" => true,
        "author_id" => user.id
      })

    IO.puts("Plugin created with id: #{plugin.id}")

  plugin ->
    IO.puts("Plugin '#{plugin_name}' already exists (id: #{plugin.id}), updating...")
    {:ok, plugin} =
      Plugins.update_plugin(plugin, %{
        "game_def" => game_def,
        "card_db" => card_db,
        "version" => plugin.version + 1
      })

    IO.puts("Plugin updated to version #{plugin.version}")
end

IO.puts("Done! Plugin '#{plugin_name}' is ready.")
