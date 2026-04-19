########## MACROS ###########################################################################
#############################################################################################

# Requires CMake > 3.15
if(${CMAKE_VERSION} VERSION_LESS "3.15")
    message(FATAL_ERROR "The 'CMakeDeps' generator only works with CMake >= 3.15")
endif()

if(Bullet_FIND_QUIETLY)
    set(Bullet_MESSAGE_MODE VERBOSE)
else()
    set(Bullet_MESSAGE_MODE STATUS)
endif()

include(${CMAKE_CURRENT_LIST_DIR}/cmakedeps_macros.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/module-BulletTargets.cmake)
include(CMakeFindDependencyMacro)

check_build_type_defined()

foreach(_DEPENDENCY ${bullet3_FIND_DEPENDENCY_NAMES} )
    # Check that we have not already called a find_package with the transitive dependency
    if(NOT ${_DEPENDENCY}_FOUND)
        find_dependency(${_DEPENDENCY} REQUIRED ${${_DEPENDENCY}_FIND_MODE})
    endif()
endforeach()

set(Bullet_VERSION_STRING "3.25")
set(Bullet_INCLUDE_DIRS ${bullet3_INCLUDE_DIRS_RELEASE} )
set(Bullet_INCLUDE_DIR ${bullet3_INCLUDE_DIRS_RELEASE} )
set(Bullet_LIBRARIES ${bullet3_LIBRARIES_RELEASE} )
set(Bullet_DEFINITIONS ${bullet3_DEFINITIONS_RELEASE} )


# Definition of extra CMake variables from cmake_extra_variables


# Only the last installed configuration BUILD_MODULES are included to avoid the collision
foreach(_BUILD_MODULE ${bullet3_BUILD_MODULES_PATHS_RELEASE} )
    message(${Bullet_MESSAGE_MODE} "Conan: Including build module from '${_BUILD_MODULE}'")
    include(${_BUILD_MODULE})
endforeach()


include(FindPackageHandleStandardArgs)
set(Bullet_FOUND 1)
set(Bullet_VERSION "3.25")

find_package_handle_standard_args(Bullet
                                  REQUIRED_VARS Bullet_VERSION
                                  VERSION_VAR Bullet_VERSION)
mark_as_advanced(Bullet_FOUND Bullet_VERSION)

set(Bullet_FOUND 1)
set(Bullet_VERSION "3.25")
mark_as_advanced(Bullet_FOUND Bullet_VERSION)

