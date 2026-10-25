import rimadiff.cli_arguments
from rimadiff.config_reader import ConfigReader
from rimadiff.history_manager import HistoryManager
from rimadiff.rima_diff_cli import RimaDiffCli


def main():
    config = ConfigReader()
    config.ensure_config()
    config.read()

    history_manager = HistoryManager(config.history_path)
    cli = RimaDiffCli(config, history_manager)

    args = rimadiff.cli_arguments.parse_arguments(config.setup_names)
    setup_name = args.user_setup or 'default'

    if args.list_history:
        cli.list_history()
        return
    elif args.list_users:
        cli.list_users(setup_name)
        return
    elif args.list_paths:
        cli.list_paths()
        return

    print_skills = args.skills or args.all_tables
    print_xp = args.xp or args.all_tables
    print_skill_rank = args.skill_rank or args.all_tables
    print_activities = args.activities or args.all_tables
    print_activity_rank = args.activity_rank or args.all_tables
    if not (print_skills or print_xp or print_skill_rank
            or print_activities or print_activity_rank):
        print_skills = True

    cli.print_tables(
        setup_name, args.force_download, args.difference,
        print_skills, print_xp, print_skill_rank,
        print_activities, print_activity_rank
        )


if __name__ == '__main__':
    main()
