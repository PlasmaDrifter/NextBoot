# Bash completion for nboot
_nboot_completions() {
    local cur prev opts flags
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    flags="--dry-run --now --yes --all --gui --version --help -d -y -a -g -V -h"
    opts="windows win fedora nobara cachy arch ubuntu debian mint bios uefi clear list ls hide unhide restore hidden status set-default default gui ${flags}"

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${flags}" -- "${cur}") )
        return 0
    fi

    case "${prev}" in
        set-default|set|setdefault)
            COMPREPLY=( $(compgen -W "windows win fedora nobara cachy arch ubuntu debian mint uefi bios" -- "${cur}") )
            return 0
            ;;
        hide)
            COMPREPLY=( $(compgen -W "windows win fedora nobara uefi bios" -- "${cur}") )
            return 0
            ;;
        unhide|restore)
            COMPREPLY=( $(compgen -W "all uefi bios" -- "${cur}") )
            return 0
            ;;
        *)
            ;;
    esac

    COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
    return 0
}

complete -F _nboot_completions nboot
complete -F _nboot_completions nextboot
