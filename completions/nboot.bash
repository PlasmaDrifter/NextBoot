# Bash completion for nboot
_nboot_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="windows win fedora nobara bios uefi list ls status set-default gui --dry-run --now --help -d -y -h -g"

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "--dry-run --now --help --gui -d -y -h -g" -- ${cur}) )
        return 0
    fi

    case "${prev}" in
        set-default|set)
            COMPREPLY=( $(compgen -W "windows win fedora nobara" -- ${cur}) )
            return 0
            ;;
        *)
            ;;
    esac

    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    return 0
}

complete -F _nboot_completions nboot
complete -F _nboot_completions nextboot
